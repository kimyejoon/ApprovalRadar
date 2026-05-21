import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT collected_by, count(*), min(created_at), max(created_at)
        FROM businesses
        GROUP BY collected_by
    """)
    rows = cursor.fetchall()
    print("=== Group by collected_by ===")
    for r in rows:
        print(f"  Source: {str(r[0]):20s} | Count: {r[1]:8,} | Min: {r[2]} | Max: {r[3]}")
    conn.close()

if __name__ == "__main__":
    main()
