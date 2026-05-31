import sqlite3
import sys
import asyncio

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

from app.services.chng_dt_poller import poll_changes_for_date

async def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Clean sync verified cache for target license numbers
    targets = ["19810053045", "20060114564", "20110313244", "20200300646"]
    print("Clearing sync verified records for targets...")
    for t in targets:
        cursor.execute("DELETE FROM chng_dt_sync_verified WHERE license_no = ?", (t,))
        cursor.execute("DELETE FROM businesses WHERE license_no = ? AND last_event_date IN ('20260529', '20260530')", (t,))
    conn.commit()
    conn.close()
    
    # 2. Run the poller for 20260529
    print("\nRunning poll_changes_for_date('20260529')...")
    await poll_changes_for_date("20260529")
    
    # 3. Check DB to see if the changes were successfully inserted
    print("\nChecking DB for newly inserted target records on 20260529...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    for t in targets:
        rows = cursor.execute("""
            SELECT license_no, business_name, last_event_date, infer_update_type, infer_update_detail, collected_by
            FROM businesses
            WHERE license_no = ? AND last_event_date = '20260529'
        """, (t,)).fetchall()
        
        print(f"\nLicense: {t}")
        if not rows:
            print("  -> NOT FOUND in DB.")
        else:
            for r in rows:
                print(f"  -> Found: Name: {r['business_name']} | EventDate: {r['last_event_date']} | Type: {r['infer_update_type']} | Detail: {r['infer_update_detail']} | CollectedBy: {r['collected_by']}")
                
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
