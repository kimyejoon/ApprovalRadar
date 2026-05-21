import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    
    print("=== Database Tables and Row Counts ===")
    for t in tables:
        cnt = cursor.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  Table: {t:25s} | Row Count: {cnt:,}")
        
    conn.close()

if __name__ == "__main__":
    main()
