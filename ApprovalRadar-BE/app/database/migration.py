import os
import sqlite3
from app.database import ddl

def run_migrations(cursor):
    # ── 기존 license_no PK → id PK 마이그레이션 ──
    cursor.execute("PRAGMA table_info(businesses)")
    biz_cols_info = cursor.fetchall()
    # 기존 테이블의 첫 번째 컬럼이 license_no이고 pk=1이면 구버전
    if biz_cols_info and biz_cols_info[0][1] == 'license_no' and biz_cols_info[0][5] == 1:
        cursor.execute('ALTER TABLE businesses RENAME TO businesses_old')
        cursor.execute(ddl.CREATE_BUSINESSES_OLD_TABLE)
        cursor.execute(ddl.INSERT_FROM_OLD_BUSINESSES)
        cursor.execute('DROP TABLE businesses_old')
        print('[DB 마이그레이션] businesses: license_no PK → id AUTOINCREMENT + UNIQUE(license_no, last_event_date)')
    
    # 기존 테이블 구조 확인 및 마이그레이션
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crawler_state'")
    has_crawler_state = cursor.fetchone() is not None

    # Check if businesses table has columns
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
    # ── API 원본 변경 사유/전/후 저장 (CHNG_PRVNS, CHNG_BF_CN, CHNG_AF_CN) ──
    if "change_reason" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN change_reason TEXT")
    if "change_before" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN change_before TEXT")
    if "change_after" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN change_after TEXT")
    if "collected_by" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN collected_by TEXT")

    if has_crawler_state:
        cursor.execute("PRAGMA table_info(crawler_state)")
        columns = [row[1] for row in cursor.fetchall()]
        if "id" in columns and "service_id" not in columns:
            cursor.execute(ddl.CREATE_CRAWLER_STATE_NEW_TABLE)
            cursor.execute(ddl.INSERT_FROM_OLD_CRAWLER_STATE)
            cursor.execute('DROP TABLE crawler_state')
            cursor.execute('ALTER TABLE crawler_state_new RENAME TO crawler_state')
        # extra_state 컬럼 마이그레이션 (기존 테이블에 없는 경우)
        if "extra_state" not in columns:
            cursor.execute("ALTER TABLE crawler_state ADD COLUMN extra_state TEXT DEFAULT '{}'")

    # api_raw_data 기존 PK 마이그레이션
    cursor.execute("PRAGMA table_info(api_raw_data)")
    raw_cols = cursor.fetchall()
    if raw_cols and raw_cols[0][1] == 'license_no' and raw_cols[0][5] == 1:
        cursor.execute('ALTER TABLE api_raw_data RENAME TO api_raw_data_old')
        cursor.execute(ddl.CREATE_API_RAW_DATA_OLD_TABLE)
        cursor.execute(ddl.INSERT_FROM_OLD_API_RAW_DATA)
        cursor.execute('DROP TABLE api_raw_data_old')
        print('[DB 마이그레이션] api_raw_data: license_no PK → id AUTOINCREMENT')

def migrate_env_keys_to_db():
    """서버 시작 시 .env의 FOOD_SAFETY_API_KEY_* 값을 api_keys 테이블에 자동 마이그레이션.
    이미 존재하는 키는 중복 삽입하지 않습니다 (IGNORE)."""
    from database import DB_FILE
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
