import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

def main():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== DB SYSTEM_LOGS TABLE STATS ===")
    total = cursor.execute("SELECT COUNT(*) FROM system_logs").fetchone()[0]
    print(f"Total log records in DB: {total:,}")
    
    print("\n--- Daily Log Levels (May 27 ~ May 31) ---")
    rows = cursor.execute("""
        SELECT DATE(created_at) as log_date, level, COUNT(*) as cnt
        FROM system_logs
        WHERE created_at BETWEEN '2026-05-27' AND '2026-06-01'
        GROUP BY log_date, level
        ORDER BY log_date, level
    """).fetchall()
    
    for r in rows:
        print(f"Date: {r['log_date']} | Level: {r['level']:8s} | Count: {r['cnt']:,}")
        
    print("\n--- Sample DB Logs on May 29 (first 10) ---")
    rows = cursor.execute("""
        SELECT created_at, level, module, message
        FROM system_logs
        WHERE created_at LIKE '2026-05-29%'
        ORDER BY id ASC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"[{r['created_at']}] [{r['level']}] {r['module']}: {r['message']}")
        
    print("\n--- Sample DB Logs on May 30 (first 10) ---")
    rows = cursor.execute("""
        SELECT created_at, level, module, message
        FROM system_logs
        WHERE created_at LIKE '2026-05-30%'
        ORDER BY id ASC LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"[{r['timestamp']}] [{r['log_level']}] {r['logger_name']}: {r['message']}")
        
    conn.close()

if __name__ == "__main__":
    main()
