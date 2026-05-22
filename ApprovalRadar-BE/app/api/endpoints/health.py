# pyrefly: ignore [missing-import]
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("")
def health_check():
    import sqlite3
    from database import DB_FILE
    db_status = "ok"
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("SELECT 1")
        conn.close()
    except Exception:
        db_status = "error"
        
    return {
        "status": "ok",
        "db_connection": db_status,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/api-health")
def api_health():
    """식품안전나라 OpenAPI 서버 건강 상태 조회."""
    from app.services.api_health_tracker import health_tracker
    return health_tracker.get_status()


@router.get("/api-health/history")
def api_health_history(limit: int = 48):
    """시간대별 서버 상태 히스토리 (Bar Chart용). limit: 최근 N건."""
    from app.services.api_health_tracker import health_tracker
    return {"history": health_tracker.get_history(limit=limit)}
