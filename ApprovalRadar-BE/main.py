from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from database import init_db

from app.core.logger import logger
from app.api.router import api_router
from app.core.scheduler import start_scheduler, shutdown_scheduler
from app.core.events import broadcaster

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set the main event loop for broadcaster
    broadcaster.set_loop(asyncio.get_running_loop())

    # Startup logic
    logger.info("Initializing Database...")
    init_db()
    
    # 누락된 세부업종 데이터 백그라운드 백필(Backfill) 시작
    import threading
    from app.services.industry_filler import fill_missing_industry_types
    threading.Thread(target=fill_missing_industry_types, daemon=True, name="IndustryBackfillThread").start()
    
    start_scheduler()
    
    yield
    
    # Shutdown logic
    from app.core.events import shutdown_event
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

