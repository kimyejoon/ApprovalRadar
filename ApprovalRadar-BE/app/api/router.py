from fastapi import APIRouter
from app.api.endpoints import approvals, health, stream, admin

api_router = APIRouter()
api_router.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])
api_router.include_router(stream.router, prefix="/api/v1/stream", tags=["stream"])
api_router.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
