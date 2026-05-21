import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(businesses)")
    cols = cursor.fetchall()
    print("=== businesses table schema ===")
    for c in cols:
        print(f"  Column: {c[1]} | Type: {c[2]}")
    conn.close()

if __name__ == "__main__":
    main()
