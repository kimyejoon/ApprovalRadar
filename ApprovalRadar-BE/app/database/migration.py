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

    # page_scan_history: first_lcns / last_lcns 컬럼 추가 (경계 변화 감지용)
    cursor.execute("PRAGMA table_info(page_scan_history)")
    psh_cols = [row[1] for row in cursor.fetchall()]
    if "first_lcns" not in psh_cols:
        cursor.execute("ALTER TABLE page_scan_history ADD COLUMN first_lcns TEXT")
        print("[DB 마이그레이션] page_scan_history: first_lcns 컬럼 추가")
    if "last_lcns" not in psh_cols:
        cursor.execute("ALTER TABLE page_scan_history ADD COLUMN last_lcns TEXT")
        print("[DB 마이그레이션] page_scan_history: last_lcns 컬럼 추가")

    # chng_dt_poll_history: api_raw_total_count 컬럼 추가 (I2500 API 실제 total_count 저장)
    cursor.execute("PRAGMA table_info(chng_dt_poll_history)")
    cph_cols = [row[1] for row in cursor.fetchall()]
    if "api_raw_total_count" not in cph_cols:
        cursor.execute("ALTER TABLE chng_dt_poll_history ADD COLUMN api_raw_total_count INTEGER DEFAULT 0")
        print("[DB 마이그레이션] chng_dt_poll_history: api_raw_total_count 컬럼 추가")

    # ── businesses UNIQUE 키 확장: (license_no, last_event_date) → (license_no, last_event_date, change_before) ──
    # SQLite는 UNIQUE 제약을 직접 수정할 수 없어 테이블 재생성 방식으로 처리
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='businesses'")
    biz_table_sql = cursor.fetchone()
    if biz_table_sql:
        biz_sql = biz_table_sql[0] or ""
        needs_unique_migration = (
            "UNIQUE(license_no, last_event_date)" in biz_sql
            and "change_before" not in biz_sql.split("UNIQUE(license_no, last_event_date")[-1][:30]
        )
        if needs_unique_migration:
            # 1. 중간 테이블 생성 (혹시 남아있으면 DROP 후 재생성)
            cursor.execute("DROP TABLE IF EXISTS businesses_v2")
            cursor.execute(ddl.CREATE_BUSINESSES_V2_TABLE)
            # 2. 기존 데이터 이관 (ORDER BY id ASC → INSERT OR IGNORE로 중복 자동 제거)
            cursor.execute(ddl.INSERT_FROM_BUSINESSES_V1_TO_V2)
            migrated_count = cursor.rowcount
            # 3. 기존 테이블 DROP → 새 테이블 rename
            cursor.execute("DROP TABLE businesses")
            cursor.execute("ALTER TABLE businesses_v2 RENAME TO businesses")
            print(
                f"[DB 마이그레이션] businesses: UNIQUE 키 확장 완료 "
                f"(license_no, last_event_date) → (license_no, last_event_date, change_before) | "
                f"이관 {migrated_count}건"
            )


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
    for i in range(1, 51):  # 최대 50개 키 지원 (config.py와 동일)
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


def migrate_extra_state_to_page_scan_history():
    """서버 시작 시 crawler_state.extra_state의 page_* 데이터를 page_scan_history 테이블로 1회 마이그레이션.
    이미 page_scan_history에 데이터가 있으면 스킵 (멱등성 보장)."""
    import json
    import sqlite3
    from database import DB_FILE

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        # 이미 데이터가 있으면 스킵
        existing_count = conn.execute("SELECT COUNT(*) FROM page_scan_history").fetchone()[0]
        if existing_count > 0:
            return

        # crawler_state에서 extra_state 읽기
        rows = conn.execute("SELECT service_id, extra_state FROM crawler_state").fetchall()
        migrated = 0
        for row in rows:
            service_id = row["service_id"]
            extra = json.loads(row["extra_state"] or "{}")
            page_timestamps = extra.get("page_timestamps", {})
            page_labels     = extra.get("page_labels", {})
            page_industries = extra.get("page_industries", {})

            # 모든 페이지 번호 수집 (세 딕셔너리의 합집합)
            all_pages = set(page_timestamps) | set(page_labels) | set(page_industries)
            for p_str in all_pages:
                ts  = page_timestamps.get(p_str)
                lbl = page_labels.get(p_str)
                ind = page_industries.get(p_str)
                conn.execute(
                    """INSERT OR IGNORE INTO page_scan_history
                       (service_id, page_number, label, industry, last_scanned_ts)
                       VALUES (?, ?, ?, ?, ?)""",
                    (service_id, int(p_str), lbl, ind, ts)
                )
                migrated += 1

        conn.commit()
        if migrated > 0:
            print(f"[DB 마이그레이션] extra_state → page_scan_history: {migrated}개 페이지 이전 완료")
    except Exception as e:
        print(f"[DB 마이그레이션] page_scan_history 마이그레이션 실패: {e}")
    finally:
        conn.close()
