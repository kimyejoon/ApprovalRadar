import sqlite3
import os
from contextlib import contextmanager

DB_FILE = "food_safety.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # SQLite 성능 최적화 (FastAPI 비동기 환경 동시성 향상)
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')
    
    # Create businesses table with JSON columns for history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            license_no TEXT PRIMARY KEY,
            business_name TEXT,
            address TEXT,
            representative_name TEXT,
            business_status TEXT,
            license_date TEXT,
            phone_number TEXT,
            representative_history TEXT DEFAULT '[]', -- JSON array
            licensing_history TEXT DEFAULT '[]', -- JSON array
            last_event_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 1 -- 1 for True, 0 for False
        )
    ''')
    
    # 크롤러 상태 관리 테이블 (단일 행 보장)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crawler_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_total_count INTEGER DEFAULT 0,
            pivots TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 원시 API 데이터(JSON) 보관 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_raw_data (
            license_no TEXT PRIMARY KEY,
            raw_json TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # To access columns by name
    try:
        yield conn
    finally:
        conn.close()

def vacuum_db():
    from app.core.logger import logger
    logger.info("Starting SQLite DB VACUUM (Optimization)...")
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("VACUUM;")
        conn.close()
        logger.info("SQLite DB VACUUM completed successfully.")
    except Exception as e:
        logger.error(f"Failed to VACUUM DB: {e}")

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
