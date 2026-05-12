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
