import sqlite3
import os

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

if not os.path.exists(db_path):
    print("Database not found")
    exit(1)

print(f"Checking database integrity for {db_path}...")
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    result = cursor.fetchall()
    print("Integrity check result:")
    for r in result:
        print(r)
    conn.close()
except Exception as e:
    print(f"Error checking integrity: {e}")
