import asyncio
import json
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Request
# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse

from app.core.logger import logger
from app.core.events import broadcaster

router = APIRouter()

@router.get(
    "/updates",
    summary="실시간 업데이트 스트림 (SSE)",
    description="""
프론트엔드에서 Server-Sent Events(SSE) 방식으로 실시간 알림을 수신하는 엔드포인트입니다.  
이 주소를 프론트엔드의 `EventSource` API 등에 연결해두면 서버로부터 실시간 알림 텍스트를 스트리밍으로 받게 됩니다.

### 수신 가능한 시그널 목록 (Event Data)

1. **연결 유지용 Ping (Heartbeat)**
   - **실제 수신 데이터:** `data: {"type": "PING", "message": "현재 정상 연결중임 (보낼 업데이트 없음)"}`
   - **발생 주기:** 서버에 새로운 업데이트가 없을 때, 연결이 끊기지 않도록 **정확히 5초마다** 발송됩니다.
   - **프론트엔드 처리:** 이 메시지는 상태 확인용이므로 UI에 표시할 필요 없이 무시하셔도 됩니다.

2. **신규 업데이트 알림**
   - **실제 수신 데이터:** `data: {"type": "UPDATE", "message": "신규 업데이트가 발생했다"}`
   - **발생 조건:** 백엔드 크롤러가 새로운 인허가 변경분을 성공적으로 수집하여 DB에 저장한 즉시 1회 발송됩니다.
   - **프론트엔드 처리:** 이 메시지를 수신하는 즉시, 화면의 데이터를 최신화하기 위해 `/api/v1/approvals` 리스트업 API를 재호출하여 사용자에게 새로운 내역을 렌더링해주시면 됩니다.
""",
    responses={
        200: {
            "description": "SSE 스트림 정상 연결. `text/event-stream` 포맷으로 데이터가 전송됩니다.",
            "content": {
                "text/event-stream": {
                    "example": 'data: {"type": "PING", "message": "현재 정상 연결중임 (보낼 업데이트 없음)"}\n\n'
                }
            }
        }
    }
)
async def stream_updates(request: Request):
    async def event_generator():
        q = asyncio.Queue()
        broadcaster.add_queue(q)
        try:
            while True:
                # ✅ [개선] 클라이언트 연결 끊김 감지 - 좀비 커넥션/메모리 누수 방지
                if await request.is_disconnected():
                    logger.info("[SSE] 클라이언트 연결 끊김 감지 → 스트림 종료")
                    break
                try:
                    # 최대 5초 대기
                    msg = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # 5초 동안 들어온 메시지가 없으면 Ping(Heartbeat) 발송
                    ping_data = json.dumps({"type": "PING", "message": "현재 정상 연결중임 (보낼 업데이트 없음)"}, ensure_ascii=False)
                    yield f"data: {ping_data}\n\n"
        except asyncio.CancelledError:
            # 클라이언트 연결 종료 시
            pass
        finally:
            broadcaster.remove_queue(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/test-trigger")
async def test_trigger():
    """
    내부망/CLI 테스트 전용 API입니다.
    이 API가 호출되면 즉시 전체 연결된 클라이언트에게 SSE 업데이트를 전송합니다.
    """
    logger.info("Test trigger invoked via CLI or internal call.")
    update_data = json.dumps({"type": "UPDATE", "message": "신규 업데이트가 발생했다"}, ensure_ascii=False)
    broadcaster.broadcast_sync(update_data)
    return {"status": "ok", "message": "Broadcast triggered successfully."}
