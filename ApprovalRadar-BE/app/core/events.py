import asyncio
import threading
from typing import List, Set
from fastapi import WebSocket

shutdown_event = threading.Event()

class Broadcaster:
    def __init__(self):
        self.queues: List[asyncio.Queue] = []
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """FastAPI 메인 비동기 루프를 저장합니다."""
        self.loop = loop

    def add_queue(self, queue: asyncio.Queue):
        self.queues.append(queue)

    def remove_queue(self, queue: asyncio.Queue):
        if queue in self.queues:
            self.queues.remove(queue)

    def broadcast_sync(self, message: str):
        """
        동기 스레드(APScheduler, Crawler)에서 호출되어, 
        비동기 루프의 큐에 메시지를 안전하게 전달합니다.
        """
        if not self.loop:
            return
        if not self.queues:
            return
        for q in self.queues:
            self.loop.call_soon_threadsafe(q.put_nowait, message)


class LogBroadcaster:
    """WebSocket 클라이언트들에게 실시간 로그를 브로드캐스팅하는 클래스."""
    def __init__(self):
        self._sockets: Set[WebSocket] = set()
        self._lock = threading.Lock()
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def connect(self, ws: WebSocket):
        with self._lock:
            self._sockets.add(ws)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            self._sockets.discard(ws)

    def broadcast_log(self, message: str):
        """동기 스레드(Logger)에서 호출. 연결된 모든 WebSocket 클라이언트에게 전송."""
        if not self.loop or not self._sockets:
            return
        sockets_snapshot = list(self._sockets)
        async def _send_all():
            disconnected = set()
            for ws in sockets_snapshot:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.add(ws)
            with self._lock:
                self._sockets -= disconnected
        self.loop.call_soon_threadsafe(asyncio.ensure_future, _send_all())


broadcaster = Broadcaster()
log_broadcaster = LogBroadcaster()
