"""
db/setup.py — 실험용 SQLite DB 생성기

실제 food_safety.db에서 5,000건을 샘플링하거나,
더미 데이터를 생성하여 api-lab/db/lab.db 를 만든다.

사용법:
    python db/setup.py --source ../../ApprovalRadar-BE/food_safety.db  # 실제 DB 샘플링
    python db/setup.py --dummy                                          # 더미 데이터 생성
"""
import sqlite3
import argparse
import os
import sys
import random
import datetime

LAB_DB = os.path.join(os.path.dirname(__file__), "lab.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    row_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lcns_no       TEXT NOT NULL,
    bssh_nm       TEXT,
    site_addr     TEXT,
    prsdnt_nm     TEXT,
    telno         TEXT,
    induty_cd_nm  TEXT,
    prms_dt       TEXT,
    chng_dt       TEXT,
    bsn_state_nm  TEXT,
    inserted_at   TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_lcns_no ON businesses (lcns_no);
CREATE INDEX IF NOT EXISTS idx_chng_dt ON businesses (chng_dt);
"""

CHNG_DT_LOG = """
CREATE TABLE IF NOT EXISTS chng_dt_insert_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lcns_no     TEXT,
    chng_dt     TEXT,
    inserted_at TEXT,
    note        TEXT
);
"""


def create_schema(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.executescript(CHNG_DT_LOG)
    conn.commit()
    print("[setup] 스키마 생성 완료")


def sample_from_real_db(source_path: str, sample_size: int = 5000):
    """실제 food_safety.db에서 샘플링하여 lab.db에 적재."""
    if not os.path.exists(source_path):
        print(f"[error] 소스 DB 없음: {source_path}")
        sys.exit(1)

    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row

    # businesses 테이블에서 샘플링
    # 최신 CHNG_DT 기준으로 상위 + 무작위 섞어서
    rows = src.execute("""
        SELECT
            license_no   AS lcns_no,
            business_name AS bssh_nm,
            address       AS site_addr,
            representative_name AS prsdnt_nm,
            phone_number  AS telno,
            industry_type AS induty_cd_nm,
            license_date  AS prms_dt,
            last_event_date AS chng_dt,
            business_status AS bsn_state_nm
        FROM businesses
        ORDER BY RANDOM()
        LIMIT ?
    """, (sample_size,)).fetchall()

    src.close()

    if not rows:
        print("[error] 소스 DB에서 데이터를 가져올 수 없습니다.")
        sys.exit(1)

    # lab.db에 삽입 — 삽입 순서를 랜덤화하여 실제 API의 정렬 혼돈 재현
    random.shuffle(rows)

    lab = sqlite3.connect(LAB_DB)
    create_schema(lab)

    lab.executemany("""
        INSERT INTO businesses
        (lcns_no, bssh_nm, site_addr, prsdnt_nm, telno, induty_cd_nm, prms_dt, chng_dt, bsn_state_nm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (r["lcns_no"], r["bssh_nm"], r["site_addr"], r["prsdnt_nm"],
         r["telno"], r["induty_cd_nm"], r["prms_dt"], r["chng_dt"], r["bsn_state_nm"])
        for r in rows
    ])
    lab.commit()
    lab.close()

    print(f"[setup] 실제 DB 샘플링 완료: {len(rows):,}건 → {LAB_DB}")
    print(f"[setup] 삽입 순서: 랜덤 셔플 (실제 API 정렬 혼돈 재현)")


def generate_dummy(sample_size: int = 5000):
    """현실적인 더미 데이터 생성."""
    lab = sqlite3.connect(LAB_DB)
    create_schema(lab)

    INDUSTRY_TYPES = [
        "즉석판매제조·가공업", "식품제조·가공업", "식품소분업", "식품운반업",
        "식품판매업", "위탁급식영업", "제과점영업", "일반음식점영업",
        "휴게음식점영업", "단란주점영업"
    ]
    STATUSES = ["영업중", "폐업", "영업정지", "허가취소"]

    # 날짜 분포: 2023~오늘, 최근일수록 더 많이
    def random_chng_dt():
        weights = [1, 2, 5, 10, 20, 30, 40]  # 2020~2026 가중치
        years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
        year = random.choices(years, weights=weights)[0]
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        today = datetime.date.today()
        d = datetime.date(year, month, day)
        if d > today:
            d = today
        return d.strftime("%Y%m%d")

    rows = []
    for i in range(sample_size):
        lcns_no = f"{random.randint(10, 99)}{random.randint(100000, 999999)}{random.randint(100, 999)}"
        rows.append((
            lcns_no,
            f"테스트업소{i+1}",
            f"서울시 강남구 테스트로 {random.randint(1, 999)}",
            f"홍길동{i}",
            f"02-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
            random.choice(INDUSTRY_TYPES),
            f"{random.randint(2010,2025)}{random.randint(1,12):02d}{random.randint(1,28):02d}",
            random_chng_dt(),
            random.choice(STATUSES),
        ))

    # 삽입 순서: 랜덤 셔플 (chng_dt와 row_id가 불일치하도록)
    random.shuffle(rows)

    lab.executemany("""
        INSERT INTO businesses
        (lcns_no, bssh_nm, site_addr, prsdnt_nm, telno, induty_cd_nm, prms_dt, chng_dt, bsn_state_nm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    lab.commit()
    lab.close()

    print(f"[setup] 더미 데이터 생성 완료: {sample_size:,}건 → {LAB_DB}")


def print_stats():
    """생성된 lab.db 기본 통계 출력."""
    if not os.path.exists(LAB_DB):
        print("[stats] lab.db 없음 — setup 먼저 실행하세요.")
        return
    lab = sqlite3.connect(LAB_DB)
    lab.row_factory = sqlite3.Row

    total = lab.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
    min_rid = lab.execute("SELECT MIN(row_id) FROM businesses").fetchone()[0]
    max_rid = lab.execute("SELECT MAX(row_id) FROM businesses").fetchone()[0]
    chng_dist = lab.execute("""
        SELECT substr(chng_dt,1,4) AS yr, COUNT(*) AS cnt
        FROM businesses GROUP BY yr ORDER BY yr DESC LIMIT 5
    """).fetchall()

    print(f"\n{'='*50}")
    print(f"  lab.db 통계")
    print(f"{'='*50}")
    print(f"  전체 건수:  {total:,}건")
    print(f"  row_id 범위: {min_rid} ~ {max_rid}  (Gap: {max_rid - min_rid + 1 - total}건)")
    print(f"  CHNG_DT 연도 분포 (최근 5년):")
    for r in chng_dist:
        print(f"    {r['yr']}: {r['cnt']:,}건")
    print(f"{'='*50}\n")
    lab.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="api-lab DB 생성기")
    parser.add_argument("--source", type=str, help="실제 food_safety.db 경로 (샘플링 모드)")
    parser.add_argument("--dummy", action="store_true", help="더미 데이터 생성 모드")
    parser.add_argument("--size", type=int, default=5000, help="샘플 건수 (기본: 5000)")
    parser.add_argument("--reset", action="store_true", help="기존 lab.db 삭제 후 재생성")
    args = parser.parse_args()

    if args.reset and os.path.exists(LAB_DB):
        os.remove(LAB_DB)
        print(f"[setup] 기존 {LAB_DB} 삭제됨")

    if args.source:
        sample_from_real_db(args.source, args.size)
    elif args.dummy:
        generate_dummy(args.size)
    else:
        print("[setup] --source <경로> 또는 --dummy 옵션을 지정하세요.")
        parser.print_help()
        sys.exit(1)

    print_stats()
