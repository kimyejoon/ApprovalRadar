import json
import sqlite3
import csv
import sys
import os

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
json_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\0520_API_Response_B.json"
output_csv = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\compare_result_0520.csv"

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    sys.exit(1)

# Connect to database and load all businesses
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Fetch all businesses from DB
print("Fetching businesses from DB...")
db_records = {}
rows_db = cursor.execute("SELECT license_no, last_event_date, business_name FROM businesses").fetchall()
for r in rows_db:
    lcns = r["license_no"]
    if lcns not in db_records:
        db_records[lcns] = []
    db_records[lcns].append(r)

print(f"Loaded {len(db_records)} unique businesses from DB.")

# Load JSON B response
print("Loading JSON B response...")
with open(json_path, "r", encoding="utf-8") as f:
    api_data = json.load(f)

api_rows = api_data.get("I2861", {}).get("row", [])
print(f"Loaded {len(api_rows)} rows from JSON B.")

# We will analyze every row in JSON B
csv_headers = [
    "LCNS_NO", "BSSH_NM", "CHNG_DT", "CHNG_PRVNS", 
    "INDUTY_CD_NM", "SITE_ADDR", "CHNG_BF_CN", "CHNG_AF_CN", "TELNO",
    "DB_EXISTS", "DB_LAST_EVENT_DATE", "IS_MISSED", "MISSED_REASON"
]

results = []
missed_count = 0
for idx, item in enumerate(api_rows):
    lcns = item.get("LCNS_NO", "").strip()
    bssh_nm = item.get("BSSH_NM", "").strip()
    chng_dt = item.get("CHNG_DT", "").strip()
    chng_prvns = item.get("CHNG_PRVNS", "").strip()
    induty_nm = item.get("INDUTY_CD_NM", "").strip()
    site_addr = item.get("SITE_ADDR", "").strip()
    chng_bf = item.get("CHNG_BF_CN", "").strip()
    chng_af = item.get("CHNG_AF_CN", "").strip()
    telno = item.get("TELNO", "").strip()
    
    # Check if exists in DB
    db_exists = "N"
    db_last_event_date = ""
    is_missed = "N"
    missed_reason = "NONE"
    
    if lcns in db_records:
        db_exists = "Y"
        # Find the latest last_event_date in our DB for this license
        dates = [r["last_event_date"] for r in db_records[lcns] if r["last_event_date"]]
        if dates:
            db_last_event_date = max(dates)
            
        # Is it missed?
        # If the latest change date in the API (chng_dt) is newer than what we have in the DB (db_last_event_date)
        if not db_last_event_date or chng_dt > db_last_event_date:
            is_missed = "Y"
            missed_reason = "DATE_LAG"
            missed_count += 1
    else:
        # Business not in DB at all
        is_missed = "Y"
        missed_reason = "DB_MISSING"
        missed_count += 1
        
    results.append({
        "LCNS_NO": lcns,
        "BSSH_NM": bssh_nm,
        "CHNG_DT": chng_dt,
        "CHNG_PRVNS": chng_prvns,
        "INDUTY_CD_NM": induty_nm,
        "SITE_ADDR": site_addr,
        "CHNG_BF_CN": chng_bf,
        "CHNG_AF_CN": chng_af,
        "TELNO": telno,
        "DB_EXISTS": db_exists,
        "DB_LAST_EVENT_DATE": db_last_event_date,
        "IS_MISSED": is_missed,
        "MISSED_REASON": missed_reason
    })

# Write to CSV
print(f"Writing {len(results)} rows to {output_csv}...")
with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=csv_headers)
    writer.writeheader()
    writer.writerows(results)

print(f"Done! Found {missed_count} missed records.")
conn.close()
