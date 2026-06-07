import sqlite3
import os

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

targets = ['20010115326', '20230517153', '20230594402', '20250697083']

for t in targets:
    print(f"\n--- Checking DB records for License {t} ---")
    rows = cursor.execute("SELECT id, license_no, business_name, last_event_date, infer_update_type, infer_update_detail, change_before, change_after, created_at FROM businesses WHERE license_no = ?", (t,)).fetchall()
    print(f"Count of rows in DB: {len(rows)}")
    for r in rows:
        print(f" ID: {r['id']}")
        print(f"  Name: {r['business_name']}")
        print(f"  Event Date: {r['last_event_date']}")
        print(f"  Infer Update Type: {r['infer_update_type']}")
        print(f"  Infer Detail: {r['infer_update_detail']}")
        print(f"  Change Before: {r['change_before']}")
        print(f"  Change After: {r['change_after']}")
        print(f"  Created At: {r['created_at']}")

conn.close()
