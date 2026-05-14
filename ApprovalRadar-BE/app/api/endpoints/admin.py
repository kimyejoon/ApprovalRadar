import asyncio
import json
import os
import requests as http_requests
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from app.core.logger import logger
from app.core.config import settings
from app.core.events import log_broadcaster
from database import get_db

router = APIRouter()


# ─── 응답 스키마 ─────────────────────────────────────────────────────────────

class KeyStatusItem(BaseModel):
    index: int
    masked_key: str
    status: str  # "active" | "exhausted" | "error"
    status_label: str
    code: Optional[str] = None
    message: Optional[str] = None


class KeyStatusResponse(BaseModel):
    total: int
    keys: List[KeyStatusItem]


class CrawlerServiceStatus(BaseModel):
    service_id: str
    last_total_count: int
    updated_at: Optional[str] = None


class CrawlerStatusResponse(BaseModel):
    services: List[CrawlerServiceStatus]


# ─── 키 상태 조회 REST 엔드포인트 ────────────────────────────────────────────

@router.get(
    "/key-status",
    response_model=KeyStatusResponse,
    summary="API 키 상태 조회",
    description="""
현재 로드된 모든 공공데이터 API 키의 상태를 실시간으로 점검하여 반환합니다.

### 응답 상태 값(`status`) 설명
- **`active`**: 정상 동작 중인 키입니다.
- **`exhausted`**: 오늘자 일일 호출 한도(INFO-300 등)가 초과된 키입니다.
- **`error`**: 통신 오류 또는 WAF 차단이 감지된 키입니다.
""",
    responses={
        200: {
            "description": "전체 API 키 상태 목록",
            "content": {
                "application/json": {
                    "example": {
                        "total": 5,
                        "keys": [
                            {
                                "index": 1,
                                "masked_key": "eb5ae***223",
                                "status": "active",
                                "status_label": "정상 동작",
                                "code": "INFO-000",
                                "message": "정상 처리되었습니다."
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def get_key_status():
    """모든 API 키의 상태를 비동기적으로 점검합니다."""
    service_id = "I2859"
    results: List[KeyStatusItem] = []

    def _check_key(idx: int, key: str) -> KeyStatusItem:
        masked = f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"
        url = f"{settings.BASE_URL}/{key}/{service_id}/{settings.DATA_TYPE}/1/1"
        try:
            res = http_requests.get(url, timeout=7).json()
            if service_id in res:
                code = res[service_id]['RESULT']['CODE']
                msg = res[service_id]['RESULT']['MSG']
                if code == "INFO-000":
                    return KeyStatusItem(index=idx, masked_key=masked, status="active", status_label="정상 동작", code=code, message=msg)
                elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in msg:
                    return KeyStatusItem(index=idx, masked_key=masked, status="exhausted", status_label="일일 한도 초과", code=code, message=msg)
                else:
                    return KeyStatusItem(index=idx, masked_key=masked, status="error", status_label=f"오류 ({code})", code=code, message=msg)
            else:
                return KeyStatusItem(index=idx, masked_key=masked, status="error", status_label="알 수 없는 응답")
        except Exception as e:
            return KeyStatusItem(index=idx, masked_key=masked, status="error", status_label=f"통신 오류", message=str(e))

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _check_key, idx + 1, key)
        for idx, key in enumerate(settings.API_KEYS)
    ]
    results = list(await asyncio.gather(*tasks))
    results.sort(key=lambda x: x.index)

    return KeyStatusResponse(total=len(results), keys=results)



# ─── 크롤러 Tail 상태 조회 REST 엔드포인트 ──────────────────────────────────

@router.get(
    "/crawler-status",
    response_model=CrawlerStatusResponse,
    summary="크롤러 상태 조회",
    description="DB에 저장된 서비스별 마지막 전체 건수(Tail)와 갱신 시각을 반환합니다.",
)
async def get_crawler_status():
    """현재 DB에 저장된 서비스별 크롤러 상태(Tail)를 반환합니다."""
    services: List[CrawlerServiceStatus] = []
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT service_id, last_total_count, updated_at FROM crawler_state ORDER BY service_id"
            )
            rows = cursor.fetchall()
            for row in rows:
                services.append(CrawlerServiceStatus(
                    service_id=row["service_id"],
                    last_total_count=row["last_total_count"],
                    updated_at=row["updated_at"],
                ))
    except Exception as e:
        logger.error(f"[crawler-status] DB 조회 오류: {e}")

    return CrawlerStatusResponse(services=services)


# ─── 로그 파일 다운로드 엔드포인트 ──────────────────────────────────────────

@router.get(
    "/logs/download",
    summary="오늘 날짜 로그 파일 다운로드",
    description="오늘 날짜(YYYYMMDD) 기준 서버 로그 파일(app_YYYYMMDD.log)을 다운로드합니다.",
)
async def download_today_log():
    """오늘 날짜 로그 파일을 텍스트 파일로 다운로드합니다."""
    today = datetime.now().strftime("%Y%m%d")
    # admin.py 기준 프로젝트 루트 탐색: app/api/endpoints/admin.py → 루트
    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    log_dir = os.path.join(base_dir, "logs")
    log_file = os.path.join(log_dir, f"app_{today}.log")

    if not os.path.isfile(log_file):
        raise HTTPException(
            status_code=404,
            detail=f"오늘({today}) 날짜의 로그 파일이 없습니다. (경로: {log_file})"
        )

    return FileResponse(
        path=log_file,
        filename=f"approvalradar_{today}.log",
        media_type="text/plain; charset=utf-8",
    )


# ─── 실시간 로그 WebSocket 엔드포인트 ────────────────────────────────────────

@router.websocket("/logs")
async def websocket_log_stream(websocket: WebSocket):
    """
    백엔드 로그를 실시간으로 스트리밍하는 WebSocket 엔드포인트입니다.

    ### 연결 방법 (JavaScript)
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/api/v1/admin/logs');
    ws.onmessage = (event) => {
        const log = JSON.parse(event.data);
        // log = { timestamp, level, message }
        console.log(log);
    };
    ```

    ### 수신 데이터 형식 (JSON)
    ```json
    {
        "timestamp": "2026-05-14 15:03:13",
        "level": "INFO",
        "message": "Starting DiffCrawler Delta Sync Job..."
    }
    ```

    ### 로그 레벨 값
    - `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
    """
    await websocket.accept()

    # 이 연결 전용 Queue 생성 후 브로드캐스터에 등록
    queue: asyncio.Queue = asyncio.Queue()
    log_broadcaster.add_queue(queue)
    logger.info(f"[WebSocket 로그] 클라이언트 연결됨. 현재 연결 수: {log_broadcaster.queue_count}")

    try:
        while True:
            try:
                # 큐에서 메시지 대기 (30초 타임아웃 → keep-alive ping)
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                # 30초 동안 로그 없으면 keep-alive ping 전송
                await websocket.send_text(json.dumps({
                    "timestamp": "",
                    "level": "PING",
                    "message": "keep-alive"
                }))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        log_broadcaster.remove_queue(queue)
        logger.info("[WebSocket 로그] 클라이언트 연결 해제.")
