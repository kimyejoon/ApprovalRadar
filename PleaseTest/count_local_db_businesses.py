import sqlite3
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cnt = cursor.execute("SELECT count(*) FROM businesses").fetchone()[0]
    print(f"Total businesses in local DB: {cnt:,}")
    
    # Query count of different industry types
    inds = cursor.execute("SELECT industry_type, count(*) FROM businesses GROUP BY industry_type").fetchall()
    print("\nBusinesses by industry type:")
    for ind, count in inds:
        print(f"  {ind}: {count:,}")
        
    conn.close()

if __name__ == "__main__":
    main()
