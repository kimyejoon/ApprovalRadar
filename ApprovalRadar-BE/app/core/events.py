import asyncio
import threading
from typing import List
from app.core.logger import logger

shutdown_event = threading.Event()

class Broadcaster:
    def __init__(self):
        self.queues: List[asyncio.Queue] = []
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """FastAPI 메인 비동기 루프를 저장합니다."""
        self.loop = loop
        logger.info("Broadcaster main event loop initialized.")

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
            logger.warning("Broadcaster loop is not set. Cannot broadcast message.")
            return

        if not self.queues:
            # 연결된 클라이언트가 없으면 무시
            return

        for q in self.queues:
            # 크로스 스레드 충돌 방지를 위해 call_soon_threadsafe 사용
            self.loop.call_soon_threadsafe(q.put_nowait, message)

broadcaster = Broadcaster()
