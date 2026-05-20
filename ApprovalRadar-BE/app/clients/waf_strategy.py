import asyncio
import threading

class WafStrategy:
    # ─── 키별 동시 요청 방지 Semaphore (클래스 레벨 공유) ──────────────────
    _key_semaphores: dict[str, threading.Semaphore] = {}
    _key_sem_lock: threading.Lock = threading.Lock()

    # WAF 전용 재시도 최대 횟수
    _MAX_WAF_RETRIES: int = 10
    _WAF_WAIT_STEP: float = 30.0
    _WAF_WAIT_CAP: float = 120.0

    @classmethod
    def get_key_semaphore(cls, api_key: str) -> threading.Semaphore:
        with cls._key_sem_lock:
            if api_key not in cls._key_semaphores:
                cls._key_semaphores[api_key] = threading.Semaphore(1)
            return cls._key_semaphores[api_key]

    @staticmethod
    async def sleep_backoff(backoff: float) -> float:
        await asyncio.sleep(backoff)
        return min(backoff * 2, 10.0)
