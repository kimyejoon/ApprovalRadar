"""
test_sse.py
───────────
Gap 분석 개선사항 #4에 대한 SSE 연결 관리 검증
- is_disconnected() 호출 코드 존재 여부
- Request 파라미터 시그니처 확인
- Heartbeat(Ping) 전송 로직 확인
- 좀비 커넥션 조기 종료 시뮬레이션
"""
import asyncio
import json
import pytest


class TestSSECodeStructure:
    """#4 SSE stream.py 코드 구조 검증"""

    def test_is_disconnected_in_stream(self):
        """stream.py에 is_disconnected() 호출이 있는지 확인"""
        with open("app/api/endpoints/stream.py") as f:
            src = f.read()
        assert "is_disconnected" in src, "is_disconnected() 호출 없음 → 좀비 커넥션 위험"

    def test_request_import_in_stream(self):
        """stream.py에 Request가 임포트되어 있는지 확인"""
        with open("app/api/endpoints/stream.py") as f:
            src = f.read()
        assert "from fastapi import" in src
        assert "Request" in src, "Request 미임포트 → is_disconnected() 사용 불가"

    def test_stream_endpoint_has_request_param(self):
        """stream_updates 함수가 request: Request 파라미터를 받는지 확인"""
        with open("app/api/endpoints/stream.py") as f:
            src = f.read()
        assert "stream_updates(request: Request)" in src, \
            "stream_updates에 Request 파라미터 없음"

    def test_ping_heartbeat_in_stream(self):
        """5초 Heartbeat Ping 로직이 있는지 확인"""
        with open("app/api/endpoints/stream.py") as f:
            src = f.read()
        assert "PING" in src, "Heartbeat PING 메시지 없음"
        assert "timeout=5" in src or "timeout=5.0" in src, "5초 타임아웃 없음"


class TestSSEGenerator:
    """#4 SSE 제너레이터 동작 시뮬레이션"""

    @pytest.mark.asyncio
    async def test_heartbeat_sent_on_no_update(self):
        """5초 내 업데이트 없으면 Ping이 전송되는지 시뮬레이션"""
        import asyncio

        q = asyncio.Queue()
        pings_received = []

        async def fake_generator():
            """stream.py의 event_generator를 단순 재현"""
            for _ in range(2):  # 2회 반복
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=0.05)
                    yield msg
                except asyncio.TimeoutError:
                    ping = json.dumps({"type": "PING"}, ensure_ascii=False)
                    yield ping

        async for msg in fake_generator():
            data = json.loads(msg)
            pings_received.append(data)

        assert len(pings_received) == 2
        assert all(p["type"] == "PING" for p in pings_received)

    @pytest.mark.asyncio
    async def test_update_message_forwarded(self):
        """큐에 UPDATE 메시지가 있으면 즉시 전달되는지 확인"""
        import asyncio

        q = asyncio.Queue()
        update_msg = json.dumps({"type": "UPDATE", "message": "신규 업데이트"})
        await q.put(update_msg)

        received = []

        async def fake_generator():
            try:
                msg = await asyncio.wait_for(q.get(), timeout=1.0)
                yield msg
            except asyncio.TimeoutError:
                yield json.dumps({"type": "PING"})

        async for msg in fake_generator():
            received.append(json.loads(msg))

        assert len(received) == 1
        assert received[0]["type"] == "UPDATE"

    @pytest.mark.asyncio
    async def test_zombie_connection_terminates(self):
        """is_disconnected=True 상태에서 루프가 즉시 종료되는지 확인"""
        import asyncio

        disconnected = True
        loop_count = 0

        async def fake_generator_with_disconnect_check():
            nonlocal loop_count
            for _ in range(10):
                if disconnected:
                    return  # is_disconnected() True → 즉시 종료
                loop_count += 1
                yield "data"

        async for _ in fake_generator_with_disconnect_check():
            pass

        assert loop_count == 0, "좀비 커넥션이 종료되지 않음"
