import sqlite3
import os
from app.database import ddl
from app.database.migration import run_migrations, migrate_env_keys_to_db, migrate_extra_state_to_page_scan_history

def init_db():
    from database import DB_FILE
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # SQLite 성능 최적화 (FastAPI 비동기 환경 동시성 향상)
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')
    
    # Create tables
    cursor.execute(ddl.CREATE_BUSINESSES_TABLE)
    
    # Run migrations
    run_migrations(cursor)
    
    cursor.execute(ddl.CREATE_BUSINESS_MEMOS_TABLE)
    cursor.execute(ddl.CREATE_INDEX_MEMOS)
    
    cursor.execute(ddl.CREATE_CHNG_DT_POLL_HISTORY_TABLE)
    cursor.execute(ddl.CREATE_INDEX_POLL_DATE)
    
    cursor.execute(ddl.CREATE_CRAWLER_STATE_TABLE)
    cursor.execute(ddl.CREATE_API_RAW_DATA_TABLE)
    cursor.execute(ddl.CREATE_SYSTEM_LOGS_TABLE)
    
    # Indexes
    cursor.execute(ddl.CREATE_INDEX_LAST_EVENT_DATE)
    cursor.execute(ddl.CREATE_INDEX_CREATED_AT)
    cursor.execute(ddl.CREATE_INDEX_BUSINESS_NAME)
    cursor.execute(ddl.CREATE_INDEX_INFER_UPDATE_TYPE)
    cursor.execute(ddl.CREATE_INDEX_LICENSE_DATE_TYPE)  # EXISTS 서브쿼리 최적화
    cursor.execute(ddl.CREATE_INDEX_INDUSTRY_TYPE)
    cursor.execute(ddl.CREATE_INDEX_LOGS_LEVEL)
    cursor.execute(ddl.CREATE_INDEX_LOGS_CREATED_AT)
    
    cursor.execute(ddl.CREATE_API_KEY_USAGE_TABLE)
    cursor.execute(ddl.CREATE_API_KEYS_TABLE)
    cursor.execute(ddl.CREATE_TAIL_HISTORY_TABLE)
    cursor.execute(ddl.CREATE_SMART_SWEEP_CACHE_TABLE)
    cursor.execute(ddl.CREATE_SMART_SWEEP_LOG_TABLE)
    cursor.execute(ddl.CREATE_API_KEY_USAGE_BY_SERVICE_TABLE)
    cursor.execute(ddl.CREATE_PAGE_SCAN_HISTORY_TABLE)
    cursor.execute(ddl.CREATE_API_HEALTH_LOG_TABLE)

    conn.commit()
    conn.close()
    
    # .env에 있는 키를 DB로 자동 마이그레이션 (최초 1회)
    migrate_env_keys_to_db()
    # extra_state JSON의 page 데이터를 page_scan_history 테이블로 마이그레이션 (최초 1회)
    migrate_extra_state_to_page_scan_history()

