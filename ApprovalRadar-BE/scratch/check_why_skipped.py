import sqlite3
import sys

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def check_sync_verified():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== Checking chng_dt_sync_verified for targets ===")
    
    targets = ["19810053045", "20060114564", "20110313244", "20200300646"]
    
    for t in targets:
        rows = cursor.execute("""
            SELECT * FROM chng_dt_sync_verified WHERE license_no = ?
        """, (t,)).fetchall()
        print(f"\nLicense: {t}")
        if not rows:
            print("  No sync verified record.")
        else:
            for r in rows:
                print(f"  TargetDate: {r['target_date']} | VerifiedAt: {r['verified_at']}")
                
    conn.close()

if __name__ == "__main__":
    check_sync_verified()
