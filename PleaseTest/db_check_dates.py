import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== DB 내 최근 last_event_date 건수 분포 (최신순 15개) ===")
rows = cursor.execute(
    "SELECT last_event_date, COUNT(*) FROM businesses "
    "GROUP BY last_event_date "
    "ORDER BY last_event_date DESC LIMIT 15"
).fetchall()
for r in rows:
    print(f"  날짜: {r[0]} | 건수: {r[1]}건")

print("\n=== DB 내 최근 created_at 분포 (최신순 10개) ===")
rows = cursor.execute(
    "SELECT id, license_no, business_name, last_event_date, created_at, collected_by "
    "FROM businesses ORDER BY id DESC LIMIT 10"
).fetchall()
for r in rows:
    print(f"  ID: {r[0]} | LCNS: {r[1]} | 상호: {r[2]} | event_date: {r[3]} | 생성일: {r[4]} | collected_by: {r[5]}")

conn.close()
