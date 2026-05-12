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
            last_event_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 1,
            update_type TEXT,
            prev_business_status TEXT,
            prev_representative_name TEXT,
            prev_business_name TEXT
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
    
    # 시스템 로깅 테이블 (DB 로깅용)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT,
            module TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 성능 최적화를 위한 인덱스 생성
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_businesses_last_event_date ON businesses (last_event_date);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_businesses_created_at ON businesses (created_at);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_businesses_business_name ON businesses (business_name);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs (level);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs (created_at);')
    
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

def backup_db():
    from app.core.logger import logger
    import shutil
    import datetime
    import time
    
    logger.info("Starting SQLite DB Local Backup...")
    try:
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"food_safety_backup_{timestamp}.db")
        
        # 안전한 백업을 위해 DB에 Shared Lock을 걸고 복사
        conn = sqlite3.connect(DB_FILE)
        bck = sqlite3.connect(backup_file)
        with bck:
            conn.backup(bck)
        bck.close()
        conn.close()
        
        logger.info(f"SQLite DB Backup completed successfully: {backup_file}")
        
        # 최근 7일치 백업만 유지 (오래된 백업 삭제 로직)
        now = time.time()
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                if os.stat(file_path).st_mtime < now - 7 * 86400:
                    os.remove(file_path)
                    logger.info(f"Deleted old backup: {filename}")
                    
    except Exception as e:
        logger.error(f"Failed to backup DB: {e}")

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
