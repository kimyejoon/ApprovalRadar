import asyncio
import threading
from collections import deque
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
    
    - broadcast_log(): 동기 스레드에서 호출, call_soon_threadsafe로 Queue에 안전 전달
    - add_queue(): 신규 연결 시 최근 {LOG_BUFFER_SIZE}건 버퍼 자동 재전송 (과거 로그 즉시 표시)
    """
    LOG_BUFFER_SIZE = 200  # 연결 시 재전송할 최근 로그 건수

    def __init__(self):
        self._queues: List[asyncio.Queue] = []
        self._lock = threading.Lock()
        self.loop = None
        self._buffer: deque = deque(maxlen=self.LOG_BUFFER_SIZE)  # 최근 로그 버퍼

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def add_queue(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._queues.append(queue)
        # 신규 연결 시 버퍼에 저장된 최근 로그 재전송 (과거 로그 즉시 표시)
        if self.loop:
            for msg in list(self._buffer):
                self.loop.call_soon_threadsafe(queue.put_nowait, msg)

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
        # 버퍼에 저장 (신규 연결 시 재전송용)
        self._buffer.append(message)
        with self._lock:
            queues_snapshot = list(self._queues)
        if not queues_snapshot:
            return
        for q in queues_snapshot:
            self.loop.call_soon_threadsafe(q.put_nowait, message)


broadcaster = Broadcaster()
log_broadcaster = LogBroadcaster()
