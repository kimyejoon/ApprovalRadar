import asyncio
import json
import requests as http_requests
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List

from app.core.logger import logger
from app.core.config import settings
from app.core.events import log_broadcaster

router = APIRouter()


# ─── 응답 스키마 ─────────────────────────────────────────────────────────────

class KeyStatusItem(BaseModel):
    index: int
    masked_key: str
    status: str  # "active" | "exhausted" | "error"
    status_label: str
    code: str | None = None
    message: str | None = None


class KeyStatusResponse(BaseModel):
    total: int
    keys: List[KeyStatusItem]


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
    log_broadcaster.connect(websocket)
    logger.info(f"[WebSocket 로그] 클라이언트 연결됨. 현재 연결 수: {len(log_broadcaster._sockets)}")

    try:
        # 연결 유지: 클라이언트가 끊을 때까지 대기
        while True:
            await asyncio.sleep(30)
            # Keep-alive ping
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
        log_broadcaster.disconnect(websocket)
        logger.info("[WebSocket 로그] 클라이언트 연결 해제.")
