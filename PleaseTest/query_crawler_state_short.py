import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT service_id, last_total_count, updated_at FROM crawler_state")
    for r in cursor.fetchall():
        print(f"SVC: {r[0]} | LastTotalCount: {r[1]} | UpdatedAt: {r[2]}")
    conn.close()

if __name__ == "__main__":
    main()
