import sqlite3
import json
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
json_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\0520_API_Response_B.json"

if not os.path.exists(db_path):
    print("Database not found")
    sys.exit(1)

# 1. DB에서 2026-05-20에 해당하는 변동 레코드 조회
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# YYYYMMDD 또는 YYYY-MM-DD 포맷을 모두 감안하여 조회
db_rows = cursor.execute(
    "SELECT license_no, business_name, last_event_date FROM businesses WHERE last_event_date = '20260520'"
).fetchall()

print(f"📊 DB 내 20260520 변경건 총 수: {len(db_rows)}건")
db_licenses_0520 = {r["license_no"]: r["business_name"] for r in db_rows}

# 2. JSON B 로드
with open(json_path, "r", encoding="utf-8") as f:
    api_data = json.load(f)
api_rows = api_data.get("I2861", {}).get("row", [])
api_licenses = {r.get("LCNS_NO") for r in api_rows if r.get("LCNS_NO")}

# 3. DB에 저장된 20260520 변경 건 중 JSON B에 포함되어 있는 것이 있는지 교차 체크
match_count = 0
not_match_samples = []
for lcns, name in db_licenses_0520.items():
    if lcns in api_licenses:
        match_count += 1
    else:
        if len(not_match_samples) < 5:
            not_match_samples.append((lcns, name))

print(f"🔄 교차 대조 결과:")
print(f"  - 0520 변경건 중 API 응답 B(0519 쿼리)에 포함된 건: {match_count}건")
print(f"  - 포함되지 않은 건(미탐/차단): {len(db_licenses_0520) - match_count}건")

if not_match_samples:
    print("\n⚠️ API 응답 B에 포함되지 않았던 0520 변경건 샘플:")
    for lcns, name in not_match_samples:
        print(f"  - {name} (인허가번호: {lcns})")

conn.close()
