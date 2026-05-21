# DDL statements for database initialization

CREATE_BUSINESSES_TABLE = '''
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
'''

CREATE_BUSINESSES_OLD_TABLE = '''
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
'''

INSERT_FROM_OLD_BUSINESSES = '''
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
'''

CREATE_BUSINESS_MEMOS_TABLE = '''
    CREATE TABLE IF NOT EXISTS business_memos (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        license_date  TEXT NOT NULL,
        business_name TEXT NOT NULL,
        content       TEXT NOT NULL,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(license_date, business_name)
    )
'''

CREATE_CHNG_DT_POLL_HISTORY_TABLE = '''
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
'''

CREATE_CRAWLER_STATE_NEW_TABLE = '''
    CREATE TABLE crawler_state_new (
        service_id TEXT PRIMARY KEY,
        last_total_count INTEGER DEFAULT 0,
        pivots TEXT DEFAULT '{}',
        extra_state TEXT DEFAULT '{}',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

INSERT_FROM_OLD_CRAWLER_STATE = '''
    INSERT INTO crawler_state_new (service_id, last_total_count, pivots, updated_at)
    SELECT 'I2859', last_total_count, pivots, updated_at FROM crawler_state WHERE id = 1
'''

CREATE_CRAWLER_STATE_TABLE = '''
    CREATE TABLE IF NOT EXISTS crawler_state (
        service_id TEXT PRIMARY KEY,
        last_total_count INTEGER DEFAULT 0,
        pivots TEXT DEFAULT '{}',
        extra_state TEXT DEFAULT '{}',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

CREATE_API_RAW_DATA_TABLE = '''
    CREATE TABLE IF NOT EXISTS api_raw_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_no TEXT NOT NULL,
        raw_json TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

CREATE_API_RAW_DATA_OLD_TABLE = '''
    CREATE TABLE api_raw_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_no TEXT NOT NULL,
        raw_json TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

INSERT_FROM_OLD_API_RAW_DATA = '''
    INSERT INTO api_raw_data (license_no, raw_json, fetched_at)
    SELECT license_no, raw_json, fetched_at FROM api_raw_data_old
'''

CREATE_SYSTEM_LOGS_TABLE = '''
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT,
        module TEXT,
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

CREATE_API_KEY_USAGE_TABLE = '''
    CREATE TABLE IF NOT EXISTS api_key_usage (
        key_masked    TEXT NOT NULL,
        usage_date    TEXT NOT NULL,
        call_count    INTEGER DEFAULT 0,
        exhausted     INTEGER DEFAULT 0,
        last_updated  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (key_masked, usage_date)
    )
'''

CREATE_API_KEYS_TABLE = '''
    CREATE TABLE IF NOT EXISTS api_keys (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        key_value   TEXT NOT NULL UNIQUE,
        memo        TEXT,
        is_active   INTEGER DEFAULT 1,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

CREATE_TAIL_HISTORY_TABLE = '''
    CREATE TABLE IF NOT EXISTS tail_history (
        service_id  TEXT NOT NULL,
        record_date TEXT NOT NULL,
        total_count INTEGER NOT NULL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (service_id, record_date)
    )
'''

CREATE_SMART_SWEEP_CACHE_TABLE = '''
    CREATE TABLE IF NOT EXISTS smart_sweep_cache (
        seg_start   INTEGER NOT NULL,
        seg_end     INTEGER NOT NULL,
        total_count INTEGER,
        first_chng  TEXT,
        probed_at   TEXT,
        probe_label TEXT DEFAULT "stratified",
        PRIMARY KEY (seg_start, seg_end)
    )
'''

CREATE_SMART_SWEEP_LOG_TABLE = '''
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
'''

CREATE_API_KEY_USAGE_BY_SERVICE_TABLE = '''
    CREATE TABLE IF NOT EXISTS api_key_usage_by_service (
        key_masked   TEXT NOT NULL,
        usage_date   TEXT NOT NULL,
        service_id   TEXT NOT NULL,
        call_count   INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (key_masked, usage_date, service_id)
    )
'''

# Indexes DDL
CREATE_INDEX_MEMOS = 'CREATE INDEX IF NOT EXISTS idx_business_memos_key ON business_memos (license_date, business_name);'
CREATE_INDEX_POLL_DATE = 'CREATE INDEX IF NOT EXISTS idx_chng_dt_poll_date ON chng_dt_poll_history (poll_date);'
CREATE_INDEX_LAST_EVENT_DATE = 'CREATE INDEX IF NOT EXISTS idx_businesses_last_event_date ON businesses (last_event_date);'
CREATE_INDEX_CREATED_AT = 'CREATE INDEX IF NOT EXISTS idx_businesses_created_at ON businesses (created_at);'
CREATE_INDEX_BUSINESS_NAME = 'CREATE INDEX IF NOT EXISTS idx_businesses_business_name ON businesses (business_name);'
CREATE_INDEX_INFER_UPDATE_TYPE = 'CREATE INDEX IF NOT EXISTS idx_businesses_infer_update_type ON businesses (infer_update_type);'
CREATE_INDEX_INDUSTRY_TYPE = 'CREATE INDEX IF NOT EXISTS idx_businesses_industry_type ON businesses (industry_type);'
CREATE_INDEX_LOGS_LEVEL = 'CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs (level);'
CREATE_INDEX_LOGS_CREATED_AT = 'CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs (created_at);'

CREATE_PAGE_SCAN_HISTORY_TABLE = '''
    CREATE TABLE IF NOT EXISTS page_scan_history (
        service_id      TEXT    NOT NULL,
        page_number     INTEGER NOT NULL,
        label           TEXT,
        industry        TEXT,
        last_scanned_ts INTEGER,
        first_lcns      TEXT,    -- 해당 페이지 첫 번째 레코드의 LCNS_NO (경계 변화 감지용)
        last_lcns       TEXT,    -- 해당 페이지 마지막 레코드의 LCNS_NO (경계 변화 감지용)
        PRIMARY KEY (service_id, page_number)
    )
'''

