"""
db/schema.py — api-lab 공유 스키마 & DB 유틸리티

lab.db 구조:
  - cloned_businesses: 실제 식품안전나라 I2861 API 응답 그대로 저장
                       (삽입 순서, API 페이지 위치, total_count 포함)
  - api_page_log:      각 페이지 호출 시 메타데이터 기록
                       (total_count 패턴 분석 핵심)
"""
import sqlite3
import os

LAB_DB = os.path.join(os.path.dirname(__file__), "lab.db")


def get_conn(db_path: str = LAB_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


SCHEMA = """
-- ─────────────────────────────────────────────────────────────────────────
-- 실제 식품안전나라 I2861 API 응답 클론 테이블
--
-- row_id:          SQLite 내부 AUTOINCREMENT (삽입 순서 = API 응답 순서 보존)
-- api_start_idx:   해당 레코드가 포함된 API 호출의 startIdx (e.g. 1, 1001, ...)
-- api_row_pos:     해당 페이지 내 순서 (0-based)
-- api_total_count: 해당 페이지 응답의 total_count 값 (★ 핵심: 페이지마다 다름)
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cloned_businesses (
    row_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_start_idx   INTEGER NOT NULL,       -- 호출 startIdx (페이지 그룹 식별)
    api_row_pos     INTEGER NOT NULL,       -- 페이지 내 순서 (0-based)
    api_total_count INTEGER,               -- 해당 호출의 total_count (★ 분석 핵심)

    -- I2861 실제 필드
    LCNS_NO         TEXT,                  -- 인허가번호
    BSSH_NM         TEXT,                  -- 업소명
    SITE_ADDR       TEXT,                  -- 주소
    SITE_ADDR_RDN   TEXT,                  -- 도로명주소
    PRSDNT_NM       TEXT,                  -- 대표자명
    TELNO           TEXT,                  -- 전화번호
    INDUTY_CD_NM    TEXT,                  -- 업종
    PRMS_DT         TEXT,                  -- 허가일자
    BSN_STATE_NM    TEXT,                  -- 영업상태
    CHNG_DT         TEXT,                  -- 변경일자 (★ 핵심 필드)

    -- 모든 필드를 JSON으로도 보관 (알 수 없는 추가 필드 대비)
    raw_json        TEXT,

    fetched_at      TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_clone_lcns ON cloned_businesses (LCNS_NO);
CREATE INDEX IF NOT EXISTS idx_clone_chng_dt ON cloned_businesses (CHNG_DT);
CREATE INDEX IF NOT EXISTS idx_clone_api_start ON cloned_businesses (api_start_idx);
CREATE INDEX IF NOT EXISTS idx_clone_row_pos ON cloned_businesses (api_start_idx, api_row_pos);

-- ─────────────────────────────────────────────────────────────────────────
-- 페이지별 호출 메타데이터 로그
-- total_count가 페이지마다 어떻게 다른지 추적하는 핵심 테이블
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_page_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id      TEXT NOT NULL,          -- I2861, I2500 등
    start_idx       INTEGER NOT NULL,
    end_idx         INTEGER NOT NULL,
    total_count     INTEGER,               -- API 응답의 total_count (★)
    returned_count  INTEGER,               -- 실제 반환된 row 건수
    result_code     TEXT,                  -- INFO-000, INFO-200 등
    chng_dt_filter  TEXT,                  -- CHNG_DT 파라미터 (있으면)
    elapsed_ms      INTEGER,               -- 응답 시간 (ms)
    fetched_at      TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_page_log_start ON api_page_log (start_idx);
CREATE INDEX IF NOT EXISTS idx_page_log_svc ON api_page_log (service_id, start_idx);
"""


def init_db(db_path: str = LAB_DB):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[schema] DB 초기화 완료: {db_path}")


def print_stats(db_path: str = LAB_DB):
    if not os.path.exists(db_path):
        print(f"[stats] DB 없음: {db_path}")
        return

    conn = get_conn(db_path)
    total = conn.execute("SELECT COUNT(*) FROM cloned_businesses").fetchone()[0]
    pages = conn.execute("SELECT COUNT(DISTINCT api_start_idx) FROM cloned_businesses").fetchone()[0]

    if total == 0:
        print("[stats] 데이터 없음 — fetch_real_data.py 먼저 실행하세요.")
        conn.close()
        return

    # total_count 분포
    tc_stats = conn.execute("""
        SELECT start_idx, total_count, returned_count
        FROM api_page_log
        ORDER BY start_idx
    """).fetchall()

    print(f"\n{'='*60}")
    print(f"  lab.db 통계")
    print(f"{'='*60}")
    print(f"  cloned_businesses: {total:,}건 ({pages}페이지)")

    if tc_stats:
        print(f"\n  ★ 페이지별 total_count (핵심 관찰):")
        for r in tc_stats:
            bar = "█" * min(int((r["total_count"] or 0) / 200), 20) if r["total_count"] else ""
            print(f"    start={r['start_idx']:>5} | total_count={str(r['total_count']):>8} | 반환={r['returned_count']:>5} {bar}")
        tc_values = [r["total_count"] for r in tc_stats if r["total_count"]]
        if tc_values:
            print(f"\n  total_count: min={min(tc_values):,}  max={max(tc_values):,}  unique_count={len(set(tc_values))}")
            if len(set(tc_values)) == 1:
                print(f"  → 모든 페이지 동일 (전체 COUNT(*) 가능성)")
            else:
                print(f"  → 페이지마다 다름 (★ 가설 B: rowid BETWEEN 범위 COUNT 가능성)")

    conn.close()
    print(f"{'='*60}\n")


if __name__ == "__main__":
    init_db()
    print_stats()
