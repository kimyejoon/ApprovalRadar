import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    targets = [
        "유가네 수유점",
        "우주횟집",
        "중독마라탕",
        "커피101스트릿",
        "미스터육회연어왕"
    ]
    
    print("=== Search in businesses table ===")
    for t in targets:
        rows = cursor.execute("SELECT * FROM businesses WHERE business_name LIKE ?", (f"%{t}%",)).fetchall()
        print(f"\nTarget: {t} | Found: {len(rows)} records")
        for r in rows:
            print(f"  ID: {r['id']} | LCNS: {r['license_no']} | Name: {r['business_name']} | EventDate: {r['last_event_date']} | CollectedBy: {r['collected_by']} | CreatedAt: {r['created_at']}")
            
    conn.close()

if __name__ == "__main__":
    main()
