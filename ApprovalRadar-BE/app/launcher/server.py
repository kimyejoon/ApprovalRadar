import threading
import time
import logging
from app.launcher.config import LOG_QUEUE

# ── 서버 스레드 제어 상태 ──────────────────────────────────────────────────────
_server_thread: threading.Thread | None = None
_shutdown_flag = threading.Event()


class QueueLogHandler(logging.Handler):
    """Python logging → Tkinter 로그 뷰어로 전달"""
    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        LOG_QUEUE.put(msg)


def _setup_log_capture() -> None:
    """백엔드 로거를 큐 핸들러에 연결"""
    handler = QueueLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                            datefmt="%H:%M:%S"))
    # 루트 로거 + uvicorn 로거
    for name in ("root", "uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name if name != "root" else "")
        if not any(isinstance(h, QueueLogHandler) for h in lg.handlers):
            lg.addHandler(handler)


def _run_server(port: int) -> None:
    """uvicorn 서버를 현재 스레드에서 실행 (blocking)"""
    try:
        import sys
        if sys.stdout is None or sys.stderr is None:
            class DummyWriter:
                def write(self, x): pass
                def flush(self): pass
                def isatty(self): return False
            if sys.stdout is None:
                sys.stdout = DummyWriter()
            if sys.stderr is None:
                sys.stderr = DummyWriter()

        import uvicorn
        from main import app

        loop = "asyncio"  # PyInstaller 번들에서 uvloop 동적 라이브러리 로딩 불안정 → asyncio 고정

        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=port,
            loop=loop,
            log_level="info",
        )
        server = uvicorn.Server(config)

        # 종료 플래그 감지 스레드
        def _watch_shutdown() -> None:
            _shutdown_flag.wait()
            server.should_exit = True

        threading.Thread(target=_watch_shutdown, daemon=True).start()
        server.run()
    except BaseException as e:
        import traceback
        LOG_QUEUE.put(f"[ERROR] Server Thread Exception:\n{traceback.format_exc()}")


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    """서버가 준비될 때까지 대기. 준비되면 True 반환."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False
