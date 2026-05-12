from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db

from app.core.logger import logger
from app.api.router import api_router
from app.core.scheduler import start_scheduler, shutdown_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Initializing Database...")
    init_db()
    
    start_scheduler()
    
    yield
    
    # Shutdown logic
    shutdown_scheduler()

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

