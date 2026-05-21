import sqlite3

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get table info
info = cursor.execute("PRAGMA table_info(api_keys)").fetchall()
for col in info:
    print(f"Col: {col[1]} ({col[2]})")

conn.close()
