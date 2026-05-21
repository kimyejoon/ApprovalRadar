import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Check for 20260045732
    row = cursor.execute("SELECT * FROM businesses WHERE license_no = '20260045732'").fetchone()
    print("Maison Once Year in businesses:")
    print(row)
    
    # Check for change logs
    change_rows = cursor.execute("SELECT * FROM approvals WHERE license_no = '20260045732'").fetchall()
    print("\nApprovals for this license:")
    for r in change_rows:
        print(r)
    conn.close()

if __name__ == "__main__":
    main()
