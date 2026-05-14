from fastapi import FastAPI
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
    allow_origins=["*"], # In production, restrict this to specific origins
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

