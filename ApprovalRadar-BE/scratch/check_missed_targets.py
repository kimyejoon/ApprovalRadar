import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

targets = [
    "유가네 수유점",
    "유가네",
    "우주횟집",
    "미스터육회연어왕",
    "커피101스트릿",
]

def search_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== Searching for Targets in Businesses Table ===")
    
    for t in targets:
        print(f"\nQuerying: %{t}%")
        rows = cursor.execute("""
            SELECT license_no, business_name, representative_name, address, last_event_date, infer_update_type, infer_update_detail, created_at, collected_by
            FROM businesses
            WHERE business_name LIKE ? OR prev_business_name LIKE ?
        """, (f"%{t}%", f"%{t}%")).fetchall()
        
        if not rows:
            print("  No records found.")
        else:
            for r in rows:
                print(f"  Name: {r['business_name']} | LCNS: {r['license_no']} | Owner: {r['representative_name']} | EventDate: {r['last_event_date']} | Type: {r['infer_update_type']} | Detail: {r['infer_update_detail']} | CollectedBy: {r['collected_by']} | Created: {r['created_at']}")
                
    conn.close()

if __name__ == "__main__":
    search_db()
