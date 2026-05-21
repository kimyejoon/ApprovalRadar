import sqlite3
import json
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM crawler_state")
    rows = cursor.fetchall()
    print("=== crawler_state table contents ===")
    for r in rows:
        print(f"Service ID: {r['service_id']}")
        print(f"  last_total_count: {r['last_total_count']}")
        print(f"  pivots: {r['pivots']}")
        print(f"  updated_at: {r['updated_at']}")
        if "extra_state" in r.keys():
            print(f"  extra_state: {r['extra_state']}")
        print("-" * 40)
    conn.close()

if __name__ == "__main__":
    main()
