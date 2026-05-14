# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import signal
import os as _os
from database import init_db

from app.core.logger import logger
from app.api.router import api_router
from app.core.scheduler import start_scheduler, shutdown_scheduler
from app.core.events import broadcaster, log_broadcaster, shutdown_event

# ALLOWED_ORIGINS: 쉼표(,)로 구분된 허용 오리진 목록 (.env에서 설정)
# 예시) ALLOWED_ORIGINS=https://approvalradar.com,https://www.approvalradar.com
# 미설정 시 개발용 localhost 기본값 사용 (프로덕션에서는 반드시 명시)
_raw_origins = _os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

def _handle_sigint(signum, frame):
    """Ctrl+C 즉시 강제 종료 핸들러. SSE 연결이 uvicorn을 block하는 경우를 방지."""
    logger.info("SIGINT/SIGTERM 수신: 모든 스레드를 즉시 강제 종료합니다.")
    shutdown_event.set()
    _os._exit(0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    # SSE 브로드캐스터 루프 설정
    broadcaster.set_loop(loop)
    logger.info("Broadcaster main event loop initialized.")
    # WebSocket 로그 브로드캐스터 루프 설정
    log_broadcaster.set_loop(loop)
    logger.info("LogBroadcaster main event loop initialized.")

    # uvicorn access/error 로거도 WebSocket으로 전달
    # → "INFO: 127.0.0.1:... GET /..." 같은 uvicorn 로그가 프론트 터미널에 표시됨
    import logging
    from app.core.logger import WebSocketLogHandler
    _ws_handler = WebSocketLogHandler()
    _ws_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    )
    for _log_name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        _uv_logger = logging.getLogger(_log_name)
        # 중복 추가 방지
        if not any(isinstance(h, WebSocketLogHandler) for h in _uv_logger.handlers):
            _uv_logger.addHandler(_ws_handler)
    logger.info("uvicorn 로거 → WebSocket 핸들러 연결 완료.")

    # Startup logic
    logger.info("Initializing Database...")
    init_db()
    
    # 누락된 세부업종 데이터 백그라운드 백필(Backfill) 시작
    import threading
    from app.services.industry_filler import fill_missing_industry_types
    threading.Thread(target=fill_missing_industry_types, daemon=True, name="IndustryBackfillThread").start()
    
    # 즉시 종료 시그널 핸들러 등록 (Ctrl+C가 SSE 연결로 인해 block되는 현상 방지)
    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)
    
    start_scheduler()
    
    yield
    
    # Shutdown logic (시그널 핸들러가 먼저 잡아서 이 코드는 거의 실행되지 않음)
    shutdown_event.set()
    shutdown_scheduler()

app = FastAPI(title="Food Safety Data API", lifespan=lifespan)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # .env의 ALLOWED_ORIGINS 환경변수로 제어
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Food Safety Data API"}

# Include API Router
app.include_router(api_router)

