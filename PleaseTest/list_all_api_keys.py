import sqlite3

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

keys = cursor.execute("SELECT id, key_value, memo, is_active FROM api_keys").fetchall()
print(f"Total keys: {len(keys)}")
for k in keys:
    print(f"ID: {k[0]} | Key: {k[1]} | Memo: {k[2]} | Active: {k[3]}")

conn.close()
