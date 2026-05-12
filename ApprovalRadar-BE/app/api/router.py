from fastapi import APIRouter
from app.api.endpoints import approvals, health

api_router = APIRouter()
api_router.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
