import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\food_safety.db"
conn = sqlite3.connect(db_path)

# List tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])

# Check if there's a record with event_date between 20260518 and 20260520
print("\n=== event_date >= 20260518 ===")
rows = conn.execute("""
    SELECT license_no, business_name, last_event_date, infer_update_type, updated_at, created_at 
    FROM businesses 
    WHERE last_event_date >= '20260518' 
    ORDER BY last_event_date DESC, updated_at DESC
    LIMIT 10
""").fetchall()
for r in rows:
    print(f"  {r[0]} | {r[1][:15]} | event={r[2]} | {r[3]} | updated={r[4]} | created={r[5]}")

# Total 20260518
c = conn.execute("SELECT COUNT(*) FROM businesses WHERE last_event_date = '20260518'").fetchone()
print(f"\n20260518 total: {c[0]}")

# Check created_at for the range scan batch
print("\n=== created_at around 22:17 ===")
rows = conn.execute("""
    SELECT license_no, business_name, last_event_date, created_at 
    FROM businesses 
    WHERE created_at >= '2026-05-19T22:17' 
    ORDER BY created_at DESC LIMIT 10
""").fetchall()
print(f"New records created at 22:17+: {len(rows)}")
for r in rows:
    marker = " *** TODAY ***" if r[2] == "20260519" else ""
    print(f"  {r[0]} | {r[1][:15]} | event={r[2]} | created={r[3]}{marker}")

conn.close()
