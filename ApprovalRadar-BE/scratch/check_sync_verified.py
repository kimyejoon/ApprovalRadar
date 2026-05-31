import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    targets = {
        "19810053045": "유가네 수유점",
        "20060114564": "우주횟집",
        "20000358305": "중독마라탕",
        "20200300646": "커피101스트릿(옥길점)",
        "20110313244": "미스터육회연어왕 안산점"
    }
    
    print("=== Checking chng_dt_sync_verified table ===")
    for lcns, name in targets.items():
        rows = cursor.execute("SELECT * FROM chng_dt_sync_verified WHERE license_no = ?", (lcns,)).fetchall()
        print(f"\nLCNS: {lcns} | Name: {name} | Found {len(rows)} sync_verified records")
        for r in rows:
            print(f"  - Target Date: {r['target_date']} | Verified At: {r['verified_at']}")
            
    conn.close()

if __name__ == "__main__":
    main()
