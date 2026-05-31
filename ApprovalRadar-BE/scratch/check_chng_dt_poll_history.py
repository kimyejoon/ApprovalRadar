import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== chng_dt_poll_history stats ===")
    total = cursor.execute("SELECT COUNT(*) FROM chng_dt_poll_history").fetchone()[0]
    print(f"Total entries: {total}")
    
    print("\n=== Recent 20 Polling Histories ===")
    rows = cursor.execute("SELECT * FROM chng_dt_poll_history ORDER BY id DESC LIMIT 20").fetchall()
    for r in rows:
        print(f"ID: {r['id']} | Date: {r['poll_date']} | Polled At: {r['polled_at']} | API Count: {r['total_api_count']} | New: {r['new_inserted']} | Skipped: {r['already_exists']} | Raw Total Count: {r['api_raw_total_count']} | Elapsed: {r['elapsed_sec']}s")
        
    conn.close()

if __name__ == "__main__":
    main()
