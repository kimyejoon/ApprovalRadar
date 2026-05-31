import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def find_matches():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("Checking if any records exist where license_date == last_event_date...")
    
    row = cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM businesses
        WHERE license_date = last_event_date
    """).fetchone()
    
    print(f"Total records where license_date == last_event_date: {row['cnt']}")
    
    if row['cnt'] > 0:
        print("\n--- Sample records ---")
        samples = cursor.execute("""
            SELECT license_no, business_name, representative_name, license_date, last_event_date, infer_update_type, created_at
            FROM businesses
            WHERE license_date = last_event_date
            LIMIT 10
        """).fetchall()
        for s in samples:
            print(f"No: {s['license_no']} | Name: {s['business_name']} | PRMS_DT: {s['license_date']} | EventDate: {s['last_event_date']} | Type: {s['infer_update_type']}")
            
    conn.close()

if __name__ == "__main__":
    find_matches()
