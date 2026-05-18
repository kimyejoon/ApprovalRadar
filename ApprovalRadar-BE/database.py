import sqlite3
import os
import sys
import threading
from contextlib import contextmanager

# PyInstaller 번들 실행 시: exe 옆에 DB 파일 위치
# 개발 환경: 소스 파일과 같은 디렉토리에 위치
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    # macOS .app 번들 내부 구조: .app/Contents/MacOS/ApprovalRadar
    # DB/설정 파일은 .app 파일과 같은 폴더(배포 폴더)에 위치
    if (os.path.basename(_exe_dir) == 'MacOS'
            and os.path.basename(os.path.dirname(_exe_dir)) == 'Contents'):
        _BASE_DIR = os.path.abspath(os.path.join(_exe_dir, '..', '..', '..'))
    else:
        _BASE_DIR = _exe_dir  # Windows/Linux 단일 바이너리
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(_BASE_DIR, "food_safety.db")

# 스레드별 독립 커넥션 캐싱 (Connection Pool)
# - 동일 스레드 내에서는 커넥션을 재사용하여 open/close 오버헤드 제거
# - 크롤러 스레드 / FastAPI 요청 스레드가 각자 독립 커넥션을 보유하여 lock 충돌 방지
_thread_local = threading.local()


def _get_thread_conn() -> sqlite3.Connection:
    """현재 스레드의 커넥션을 반환합니다. 없으면 새로 생성합니다."""
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        _thread_local.conn = conn
    return conn


def close_thread_conn() -> None:
    """현재 스레드의 커넥션을 닫고 캐시에서 제거합니다. (테스트용)"""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        conn.close()
        _thread_local.conn = None

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
            industry_type TEXT,
            representative_history TEXT DEFAULT '[]', -- JSON array
            licensing_history TEXT DEFAULT '[]', -- JSON array
            last_event_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 1,
            update_type TEXT,
            prev_business_status TEXT,
            prev_representative_name TEXT,
            prev_business_name TEXT,
            infer_update_type TEXT,
            infer_update_detail TEXT,
            last_event_time TEXT,
            license_time TEXT,
            is_read INTEGER DEFAULT 0,
            read_at TEXT
        )
    ''')
    
    # 기존 테이블 구조 확인 및 마이그레이션
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crawler_state'")
    has_crawler_state = cursor.fetchone() is not None

    # Check if businesses table has industry_type column
    cursor.execute("PRAGMA table_info(businesses)")
    biz_columns = [row[1] for row in cursor.fetchall()]
    if "industry_type" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN industry_type TEXT")
    if "infer_update_type" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN infer_update_type TEXT")
    if "infer_update_detail" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN infer_update_detail TEXT")
    if "last_event_time" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN last_event_time TEXT")
    if "license_time" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN license_time TEXT")
    if "is_read" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN is_read INTEGER DEFAULT 0")
    if "read_at" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN read_at TEXT")
    if "representative_history" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN representative_history TEXT DEFAULT '[]'")
    if "licensing_history" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN licensing_history TEXT DEFAULT '[]'")

    # 인허가 변동건 메모 테이블 (license_date + business_name 당 1건)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS business_memos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            license_date  TEXT NOT NULL,
            business_name TEXT NOT NULL,
            content       TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(license_date, business_name)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_business_memos_key ON business_memos (license_date, business_name);')

    if has_crawler_state:
        cursor.execute("PRAGMA table_info(crawler_state)")
        columns = [row[1] for row in cursor.fetchall()]
        if "id" in columns and "service_id" not in columns:
            cursor.execute('''
                CREATE TABLE crawler_state_new (
                    service_id TEXT PRIMARY KEY,
                    last_total_count INTEGER DEFAULT 0,
                    pivots TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                INSERT INTO crawler_state_new (service_id, last_total_count, pivots, updated_at)
                SELECT 'I2859', last_total_count, pivots, updated_at FROM crawler_state WHERE id = 1
            ''')
            cursor.execute('DROP TABLE crawler_state')
            cursor.execute('ALTER TABLE crawler_state_new RENAME TO crawler_state')
    
    # 크롤러 상태 관리 테이블 (다중 API 지원)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crawler_state (
            service_id TEXT PRIMARY KEY,
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
    
    # API 키별 일일 사용량 추적 테이블
    cursor.execute('''\
        CREATE TABLE IF NOT EXISTS api_key_usage (
            key_masked    TEXT NOT NULL,
            usage_date    TEXT NOT NULL,
            call_count    INTEGER DEFAULT 0,
            exhausted     INTEGER DEFAULT 0,
            last_updated  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (key_masked, usage_date)
        )
    ''')

    # API 키 관리 테이블 (DB primary source)
    cursor.execute('''\
        CREATE TABLE IF NOT EXISTS api_keys (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key_value   TEXT NOT NULL UNIQUE,
            memo        TEXT,
            is_active   INTEGER DEFAULT 1,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 서비스 ID별 API 호출 횟수 추적 테이블 (I2859/I2861/I2500 구분)
    cursor.execute('''\
        CREATE TABLE IF NOT EXISTS api_key_usage_by_service (
            key_masked   TEXT NOT NULL,
            usage_date   TEXT NOT NULL,
            service_id   TEXT NOT NULL,
            call_count   INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (key_masked, usage_date, service_id)
        )
    ''')

    conn.commit()
    conn.close()
    
    # .env에 있는 키를 DB로 자동 마이그레이션 (최초 1회)
    _migrate_env_keys_to_db()


def _migrate_env_keys_to_db():
    """서버 시작 시 .env의 FOOD_SAFETY_API_KEY_* 값을 api_keys 테이블에 자동 마이그레이션.
    이미 존재하는 키는 중복 삽입하지 않습니다 (IGNORE)."""
    import os
    env_keys = []
    for i in range(1, 10):
        key = os.getenv(f"FOOD_SAFETY_API_KEY_{i}")
        if key:
            env_keys.append(key)
    if not env_keys:
        fallback = os.getenv("FOOD_SAFETY_API_KEY")
        if fallback:
            env_keys.append(fallback)

    if not env_keys:
        return

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        existing = {row["key_value"] for row in conn.execute("SELECT key_value FROM api_keys").fetchall()}
        inserted = 0
        for key in env_keys:
            if key not in existing:
                conn.execute(
                    "INSERT INTO api_keys (key_value, memo, is_active) VALUES (?, ?, 1)",
                    (key, ".env 자동 마이그레이션")
                )
                inserted += 1
        conn.commit()
        if inserted > 0:
            print(f"[DB 마이그레이션] .env 키 {inserted}개를 api_keys 테이블에 등록했습니다.")
    finally:
        conn.close()

@contextmanager
def get_db():
    """스레드 로컬 커넥션을 반환하는 컨텍스트 매니저.
    커넥션은 스레드별로 캐싱되어 재사용됩니다.
    """
    conn = _get_thread_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise

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
