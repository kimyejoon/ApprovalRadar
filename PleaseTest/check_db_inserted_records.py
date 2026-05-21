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
    
    print("=== Created At Distribution ===")
    rows = cursor.execute("""
        SELECT date(created_at) as c_date, count(*) as cnt 
        FROM businesses 
        GROUP BY c_date 
        ORDER BY c_date DESC 
        LIMIT 20
    """).fetchall()
    for r in rows:
        print(f"  Date: {r['c_date']} | Count: {r['cnt']}")
        
    print("\n=== Records inserted today (2026-05-21) ===")
    # Print samples of today's insertions to see what they are
    rows_today = cursor.execute("""
        SELECT license_no, business_name, last_event_date, created_at, update_type, infer_update_type
        FROM businesses
        WHERE created_at >= '2026-05-21'
        LIMIT 30
    """).fetchall()
    
    total_today = cursor.execute("SELECT count(*) FROM businesses WHERE created_at >= '2026-05-21'").fetchone()[0]
    print(f"Total inserted today: {total_today} records")
    for idx, r in enumerate(rows_today):
        print(f"  {idx+1:2d} | LCNS: {r['license_no']} | Name: {r['business_name']} | EventDate: {r['last_event_date']} | Created: {r['created_at']} | Infer: {r['infer_update_type']}")
        
    # Check if there are any dummy records
    print("\n=== Dummy or Test patterns ===")
    patterns = ['%테스트%', '%test%', '%dummy%', '%더미%']
    for p in patterns:
        cnt = cursor.execute("SELECT count(*) FROM businesses WHERE business_name LIKE ?", (p,)).fetchone()[0]
        print(f"  Pattern '{p}': {cnt} records")
        if cnt > 0:
            samples = cursor.execute("SELECT license_no, business_name, created_at FROM businesses WHERE business_name LIKE ? LIMIT 5", (p,)).fetchall()
            for s in samples:
                print(f"    - LCNS: {s['license_no']} | Name: {s['business_name']} | Created: {s['created_at']}")
                
    conn.close()

if __name__ == "__main__":
    main()
