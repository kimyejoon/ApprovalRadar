# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import asyncio
import time as _time
import signal
import os as _os
import sys as _sys
import pathlib as _pathlib
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

# 헬스체크 경로는 로그에서 제외 (노이즈 방지)
_LOG_SKIP_PATHS = {"/health", "/", "/favicon.ico"}

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    모든 FastAPI 엔드포인트 호출을 로깅합니다.
    요청정보: method, path, status_code, 소요시간(ms)
    "/health" 등 유지보수용 엔드포인트는 로그 제외하여 노이즈 최소화.
    """
    async def dispatch(self, request: Request, call_next):
        start = _time.monotonic()
        response = await call_next(request)
        duration_ms = (_time.monotonic() - start) * 1000

        path = request.url.path
        if path not in _LOG_SKIP_PATHS:
            logger.info(
                f"[FastAPI] {request.method} {path} "
                f"→ {response.status_code} ({duration_ms:.1f}ms)"
            )
        return response

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
    # ✅ fill_missing_industry_types가 async def이므로 스레드 내 asyncio.run()으로 실행
    import threading
    import asyncio as _asyncio
    from app.services.industry_filler import fill_missing_industry_types
    threading.Thread(
        target=lambda: _asyncio.run(fill_missing_industry_types()),
        daemon=True,
        name="IndustryBackfillThread"
    ).start()
    
    # 즉시 종료 시그널 핸들러 등록 (Ctrl+C가 SSE 연결로 인해 block되는 현상 방지)
    # PyInstaller 환경에서 uvicorn이 서브스레드로 실행될 때는 signal 설정 불가
    import threading as _threading
    if _threading.current_thread() is _threading.main_thread():
        signal.signal(signal.SIGINT, _handle_sigint)
        signal.signal(signal.SIGTERM, _handle_sigint)
    
    start_scheduler()
    
    yield
    
    # Shutdown logic (시그널 핸들러가 먼저 잡아서 이 코드는 거의 실행되지 않음)
    shutdown_event.set()
    shutdown_scheduler()

app = FastAPI(title="Food Safety Data API", lifespan=lifespan)

# ── 요청 로깅 미들웨어 (가장 먼저 등록해야 CORS 에러 전에 로깅 가능) ──
app.add_middleware(RequestLoggingMiddleware)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # .env의 ALLOWED_ORIGINS 환경변수로 제어
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# Include API Router
app.include_router(api_router)

# ── 도메인 예외 핸들러 등록 ───────────────────────────────────────────────
from fastapi.responses import JSONResponse
from app.core.exceptions import (
    EntityNotFoundException, AlreadyExistsException, DatabaseOperationException
)

@app.exception_handler(EntityNotFoundException)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundException):
    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": exc.message}
    )

@app.exception_handler(AlreadyExistsException)
async def already_exists_handler(request: Request, exc: AlreadyExistsException):
    return JSONResponse(
        status_code=409,
        content={"status": "error", "message": exc.message}
    )

@app.exception_handler(DatabaseOperationException)
async def database_operation_handler(request: Request, exc: DatabaseOperationException):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": exc.message}
    )

# ── 프론트엔드 정적 파일 서빙 ────────────────────────────────────────────────
# 배포 빌드 시 FE dist/ 를 FastAPI 동일 포트에서 제공
# PyInstaller 번들: sys._MEIPASS 기준, 개발 환경: BE 폴더 내 dist/ 참조
if getattr(_sys, 'frozen', False):
    _static_base = _pathlib.Path(_sys._MEIPASS)  # type: ignore[attr-defined]
else:
    _static_base = _pathlib.Path(__file__).parent

_dist_dir = _static_base / "dist"
if _dist_dir.exists():
    # pyrefly: ignore [missing-import]
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_dist_dir), html=True), name="spa")
else:
    # dist/ 없는 개발 환경 폴백
    @app.get("/")
    def read_root():
        return {"message": "Welcome to the Food Safety Data API (dev mode, no FE build)"}
