import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\food_safety.db")

rows = conn.execute(
    "SELECT last_event_date, COUNT(*) as cnt FROM businesses WHERE last_event_date >= '20260518' GROUP BY last_event_date ORDER BY last_event_date"
).fetchall()
print("Recent event dates:")
for r in rows:
    print(f"  {r[0]}: {r[1]}건")

print(f"\nTotal: {conn.execute('SELECT COUNT(*) FROM businesses').fetchone()[0]}")
conn.close()
