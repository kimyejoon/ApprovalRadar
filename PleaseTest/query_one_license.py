import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query one license to see its records
    rows = cursor.execute("""
        SELECT id, license_no, business_name, last_event_date, created_at, collected_by, update_type, infer_update_type
        FROM businesses
        WHERE license_no = '20080375099'
    """).fetchall()
    
    print("=== Records for License 20080375099 ===")
    for r in rows:
        print(dict(r))
        
    conn.close()

if __name__ == "__main__":
    main()
