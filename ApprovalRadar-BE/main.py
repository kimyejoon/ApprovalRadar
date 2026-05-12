from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import math
import time
from database import init_db, vacuum_db, backup_db
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import run_scraper_job
from app.core.logger import logger
from app.api.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Initializing Database...")
    init_db()
    
    logger.info("Starting APScheduler for 10-minute scraping intervals...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scraper_job, 'interval', minutes=10)
    scheduler.add_job(vacuum_db, 'cron', day_of_week='sun', hour=3, minute=0)
    scheduler.add_job(backup_db, 'cron', hour=4, minute=0)
    scheduler.start()
    
    # Run once on startup to catch up
    run_scraper_job()
    
    yield
    
    # Shutdown logic
    logger.info("Shutting down...")
    scheduler.shutdown()

app = FastAPI(title="Food Safety Data API", lifespan=lifespan)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Food Safety Data API"}

# Include API Router
app.include_router(api_router)

