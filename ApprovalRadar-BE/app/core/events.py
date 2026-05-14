import asyncio
import threading
from typing import List

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
    """
    Queue 기반 WebSocket 로그 브로드캐스터.

    각 WebSocket 연결마다 독립적인 asyncio.Queue를 사용합니다.
    - broadcast_log()는 call_soon_threadsafe로 Queue에 메시지를 넣습니다.
    - WebSocket 엔드포인트는 자신의 Queue에서만 읽어 send_text()를 호출합니다.
    - 이 분리 덕분에 WebSocket send 동시성 문제와 소켓 상태 추적 문제가 모두 해소됩니다.
    """

    def __init__(self):
        self._queues: List[asyncio.Queue] = []
        self._lock = threading.Lock()
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def add_queue(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._queues.append(queue)

    def remove_queue(self, queue: asyncio.Queue) -> None:
        with self._lock:
            if queue in self._queues:
                self._queues.remove(queue)

    @property
    def queue_count(self) -> int:
        with self._lock:
            return len(self._queues)

    def broadcast_log(self, message: str) -> None:
        """
        로거 핸들러에서 호출됩니다 (동기 컨텍스트).

        call_soon_threadsafe(q.put_nowait, message)를 사용해
        이벤트 루프 스레드/백그라운드 스레드 어디서 호출해도 안전합니다.
        """
        if not self.loop:
            return
        with self._lock:
            queues_snapshot = list(self._queues)
        if not queues_snapshot:
            return
        for q in queues_snapshot:
            self.loop.call_soon_threadsafe(q.put_nowait, message)


broadcaster = Broadcaster()
log_broadcaster = LogBroadcaster()
