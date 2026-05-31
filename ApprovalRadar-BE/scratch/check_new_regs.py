import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def check_new_regs():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== Checking '신규등록' Records in DB ===")
    
    # Check total count of each infer_update_type
    rows = cursor.execute("""
        SELECT infer_update_type, COUNT(*) as cnt
        FROM businesses
        GROUP BY infer_update_type
    """).fetchall()
    
    print("\n--- Distribution of infer_update_type ---")
    for r in rows:
        print(f"Type: {r['infer_update_type']} | Count: {r['cnt']}")
        
    # Check recent 10 '신규등록' records
    print("\n--- Recent 10 '신규등록' Records ---")
    rows = cursor.execute("""
        SELECT license_no, business_name, representative_name, address, last_event_date, created_at
        FROM businesses
        WHERE infer_update_type = '신규등록'
        ORDER BY created_at DESC
        LIMIT 10
    """).fetchall()
    
    for r in rows:
        print(f"No: {r['license_no']} | Name: {r['business_name']} | Owner: {r['representative_name']} | Address: {r['address']} | EventDate: {r['last_event_date']} | Created: {r['created_at']}")
        
    conn.close()

if __name__ == "__main__":
    check_new_regs()
