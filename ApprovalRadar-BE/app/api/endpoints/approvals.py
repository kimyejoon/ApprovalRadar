from fastapi import APIRouter
from app.api.endpoints.approvals.approvals import router as approvals_main_router
from app.api.endpoints.approvals.indicators import router as indicators_router
from app.api.endpoints.approvals.memo import router as memo_router

router = APIRouter()

router.include_router(approvals_main_router)
router.include_router(indicators_router)
router.include_router(memo_router)
