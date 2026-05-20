import sqlite3
import os
def init_db():
    from database import DB_FILE
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # SQLite 성능 최적화 (FastAPI 비동기 환경 동시성 향상)
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')
    
    # Create businesses table — 동일 LCNS의 여러 인허가변동 이력을 개별 보관
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_no TEXT NOT NULL,
            business_name TEXT,
            address TEXT,
            representative_name TEXT,
            business_status TEXT,
            license_date TEXT,
            phone_number TEXT,
            industry_type TEXT,
            representative_history TEXT DEFAULT '[]',
            licensing_history TEXT DEFAULT '[]',
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
            read_at TEXT,
            UNIQUE(license_no, last_event_date)
        )
    ''')

    # ── 기존 license_no PK → id PK 마이그레이션 ──
    cursor.execute("PRAGMA table_info(businesses)")
    biz_cols_info = cursor.fetchall()
    # 기존 테이블의 첫 번째 컬럼이 license_no이고 pk=1이면 구버전
    if biz_cols_info and biz_cols_info[0][1] == 'license_no' and biz_cols_info[0][5] == 1:
        cursor.execute('ALTER TABLE businesses RENAME TO businesses_old')
        cursor.execute('''
            CREATE TABLE businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_no TEXT NOT NULL,
                business_name TEXT,
                address TEXT,
                representative_name TEXT,
                business_status TEXT,
                license_date TEXT,
                phone_number TEXT,
                industry_type TEXT,
                representative_history TEXT DEFAULT '[]',
                licensing_history TEXT DEFAULT '[]',
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
                read_at TEXT,
                UNIQUE(license_no, last_event_date)
            )
        ''')
        cursor.execute('''
            INSERT INTO businesses (
                license_no, business_name, address, representative_name,
                business_status, license_date, phone_number, industry_type,
                representative_history, licensing_history, last_event_date,
                created_at, updated_at, is_new, update_type,
                prev_business_status, prev_representative_name, prev_business_name,
                infer_update_type, infer_update_detail, last_event_time,
                license_time, is_read, read_at
            )
            SELECT
                license_no, business_name, address, representative_name,
                business_status, license_date, phone_number, industry_type,
                representative_history, licensing_history, last_event_date,
                created_at, updated_at, is_new, update_type,
                prev_business_status, prev_representative_name, prev_business_name,
                infer_update_type, infer_update_detail, last_event_time,
                license_time, is_read, read_at
            FROM businesses_old
        ''')
        cursor.execute('DROP TABLE businesses_old')
        print('[DB 마이그레이션] businesses: license_no PK → id AUTOINCREMENT + UNIQUE(license_no, last_event_date)')
    
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
    # ── API 원본 변경 사유/전/후 저장 (CHNG_PRVNS, CHNG_BF_CN, CHNG_AF_CN) ──
    if "change_reason" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN change_reason TEXT")
    if "change_before" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN change_before TEXT")
    if "change_after" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN change_after TEXT")
    if "collected_by" not in biz_columns:
        cursor.execute("ALTER TABLE businesses ADD COLUMN collected_by TEXT")

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

    # ── CHNG_DT Poller 이력 테이블 (전략C 시간별 트렌드 추적) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chng_dt_poll_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_date       TEXT NOT NULL,
            polled_at       TEXT NOT NULL,
            total_api_count INTEGER DEFAULT 0,
            new_inserted    INTEGER DEFAULT 0,
            already_exists  INTEGER DEFAULT 0,
            pages_fetched   INTEGER DEFAULT 0,
            elapsed_sec     REAL DEFAULT 0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chng_dt_poll_date ON chng_dt_poll_history (poll_date);')

    if has_crawler_state:
        cursor.execute("PRAGMA table_info(crawler_state)")
        columns = [row[1] for row in cursor.fetchall()]
        if "id" in columns and "service_id" not in columns:
            cursor.execute('''
                CREATE TABLE crawler_state_new (
                    service_id TEXT PRIMARY KEY,
                    last_total_count INTEGER DEFAULT 0,
                    pivots TEXT DEFAULT '{}',
                    extra_state TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                INSERT INTO crawler_state_new (service_id, last_total_count, pivots, updated_at)
                SELECT 'I2859', last_total_count, pivots, updated_at FROM crawler_state WHERE id = 1
            ''')
            cursor.execute('DROP TABLE crawler_state')
            cursor.execute('ALTER TABLE crawler_state_new RENAME TO crawler_state')
        # extra_state 컬럼 마이그레이션 (기존 테이블에 없는 경우)
        if "extra_state" not in columns:
            cursor.execute("ALTER TABLE crawler_state ADD COLUMN extra_state TEXT DEFAULT '{}'")

    # 크롤러 상태 관리 테이블 (다중 API 지원)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crawler_state (
            service_id TEXT PRIMARY KEY,
            last_total_count INTEGER DEFAULT 0,
            pivots TEXT DEFAULT '{}',
            extra_state TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 원시 API 데이터(JSON) 보관 테이블 — 동일 LCNS의 여러 이력을 보관
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_raw_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_no TEXT NOT NULL,
            raw_json TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # api_raw_data 기존 PK 마이그레이션
    cursor.execute("PRAGMA table_info(api_raw_data)")
    raw_cols = cursor.fetchall()
    if raw_cols and raw_cols[0][1] == 'license_no' and raw_cols[0][5] == 1:
        cursor.execute('ALTER TABLE api_raw_data RENAME TO api_raw_data_old')
        cursor.execute('''
            CREATE TABLE api_raw_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_no TEXT NOT NULL,
                raw_json TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('INSERT INTO api_raw_data (license_no, raw_json, fetched_at) SELECT license_no, raw_json, fetched_at FROM api_raw_data_old')
        cursor.execute('DROP TABLE api_raw_data_old')
        print('[DB 마이그레이션] api_raw_data: license_no PK → id AUTOINCREMENT')
    
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

    # Tail(total_count) 일별 변화 추적 테이블
    cursor.execute('''\
        CREATE TABLE IF NOT EXISTS tail_history (
            service_id  TEXT NOT NULL,
            record_date TEXT NOT NULL,
            total_count INTEGER NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (service_id, record_date)
        )
    ''')

    # SmartSweep 캐시: 세그먼트별 마지막 상태 (total_count delta + first_chng 필터)
    cursor.execute('''\
        CREATE TABLE IF NOT EXISTS smart_sweep_cache (
            seg_start   INTEGER NOT NULL,
            seg_end     INTEGER NOT NULL,
            total_count INTEGER,
            first_chng  TEXT,
            probed_at   TEXT,
            probe_label TEXT DEFAULT "stratified",
            PRIMARY KEY (seg_start, seg_end)
        )
    ''')

    # SmartSweep 실행 이력: Playground 모니터링용
    cursor.execute('''\
        CREATE TABLE IF NOT EXISTS smart_sweep_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at      TEXT NOT NULL,
            strategy    TEXT NOT NULL,
            probe_calls INTEGER DEFAULT 0,
            hot_segs    INTEGER DEFAULT 0,
            delta_segs  INTEGER DEFAULT 0,
            collected   INTEGER DEFAULT 0,
            elapsed_sec REAL DEFAULT 0.0,
            detail_json TEXT
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

    # Tail(total_count) 일별 변화 추적 테이블 (중복 쿼리 제거 및 커밋)
    conn.commit()
    conn.close()
    
    # .env에 있는 키를 DB로 자동 마이그레이션 (최초 1회)
    _migrate_env_keys_to_db()


def _migrate_env_keys_to_db():
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
