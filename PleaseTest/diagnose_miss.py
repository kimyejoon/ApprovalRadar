import sqlite3, sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
conn = sqlite3.connect(db)

# 1. 미탐 업체 LCNS가 DB에 존재하는지
targets = [
    ("빽보이피자 둔촌점",       "20230154976"),
    ("미친양꼬치 홍대직영점",    "20230092283"),
    ("호미스피자 명지대점",      "20230088005"),
    ("너도나도식당 상암DMC점",   "20250098526"),
]
print("=== 미탐 LCNS DB 존재 여부 ===")
for name, lcns in targets:
    rows = conn.execute(
        "SELECT id, license_no, business_name, last_event_date, collected_by, created_at "
        "FROM businesses WHERE license_no=?", (lcns,)
    ).fetchall()
    if rows:
        for r in rows:
            print(f"  '{name}' → DB 존재: id={r[0]}, LCNS={r[1]}, last_event={r[3]}, by={r[4]}, at={r[5]}")
    else:
        print(f"  '{name}' → ❌ DB에 없음 (LCNS={lcns})")

# 2. page_scan_history 에서 page 285 타임스탬프
print("\n=== page_scan_history P284~286 ===")
rows = conn.execute(
    "SELECT service_id, page_number, last_scanned_ts, label, industry "
    "FROM page_scan_history WHERE service_id='I2861' AND page_number BETWEEN 283 AND 286 "
    "ORDER BY page_number"
).fetchall()
for r in rows:
    ts = datetime.fromtimestamp(r[2]).strftime('%Y-%m-%d %H:%M:%S') if r[2] else "미스캔"
    print(f"  P{r[1]:4d} | {ts} | label={r[3]} | industry={r[4]}")

# 3. crawler_state에서 last_total_count 확인
print("\n=== crawler_state (I2861) ===")
row = conn.execute(
    "SELECT state_json FROM crawler_state WHERE service_id='I2861'"
).fetchone()
if row:
    import json
    s = json.loads(row[0])
    ltc = s.get('last_total_count', '?')
    extra = s.get('extra_state', {})
    boundary = extra.get('target_boundary_page', '?')
    print(f"  last_total_count: {ltc:,}" if isinstance(ltc, int) else f"  last_total_count: {ltc}")
    print(f"  target_boundary_page: {boundary}")
    print(f"  extra_state keys: {list(extra.keys())}")

# 4. STALE_THRESHOLD 설정 확인
print("\n=== .env STALE_THRESHOLD_MINUTES ===")
try:
    with open(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\.env") as f:
        for line in f:
            if 'STALE' in line or 'THRESHOLD' in line:
                print(f"  {line.strip()}")
except:
    print("  .env 읽기 실패")

# 5. page 285 주변 스캔 이력 전체
print("\n=== I2861 P283~287 상세 이력 ===")
rows = conn.execute(
    "SELECT page_number, last_scanned_ts, label FROM page_scan_history "
    "WHERE service_id='I2861' AND page_number BETWEEN 283 AND 287 ORDER BY page_number"
).fetchall()
if not rows:
    print("  해당 페이지 스캔 이력 없음")
for r in rows:
    ts = datetime.fromtimestamp(r[1]).strftime('%Y-%m-%d %H:%M:%S') if r[1] else "0"
    print(f"  P{r[0]:4d} | last_scanned={ts} | label={r[2]}")

conn.close()
