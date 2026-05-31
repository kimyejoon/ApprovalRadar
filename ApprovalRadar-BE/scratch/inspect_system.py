import sqlite3
import re
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
logs_dir = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\logs"

def analyze_db():
    print("=== DATABASE STATUS ===")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. chng_dt_poll_history stats for May 27 to 30
    print("\n--- chng_dt_poll_history (May 27 ~ May 30) ---")
    rows = cursor.execute("""
        SELECT poll_date, COUNT(*) as runs, 
               SUM(total_api_count) as total_fetched, 
               SUM(new_inserted) as total_new, 
               SUM(already_exists) as total_skipped,
               AVG(elapsed_sec) as avg_elapsed
        FROM chng_dt_poll_history
        WHERE poll_date BETWEEN '20260527' AND '20260530'
        GROUP BY poll_date
        ORDER BY poll_date
    """).fetchall()
    
    for r in rows:
        print(f"Date: {r['poll_date']} | Runs: {r['runs']} | Fetched: {r['total_fetched']:,} | New: {r['total_new']:,} | Skipped: {r['total_skipped']:,} | Avg time: {r['avg_elapsed']:.1f}s")

    # 2. Daily summary of new records in businesses table
    print("\n--- Businesses added per date (last_event_date) ---")
    rows = cursor.execute("""
        SELECT last_event_date, COUNT(*) as cnt
        FROM businesses
        WHERE last_event_date BETWEEN '20260527' AND '20260530'
        GROUP BY last_event_date
        ORDER BY last_event_date
    """).fetchall()
    for r in rows:
        print(f"Event Date: {r['last_event_date']} | Count: {r['cnt']}")
        
    # 3. Daily sync verified count
    print("\n--- Sync verified records count in DB ---")
    rows = cursor.execute("""
        SELECT target_date, COUNT(*) as cnt
        FROM chng_dt_sync_verified
        WHERE target_date BETWEEN '20260527' AND '20260530'
        GROUP BY target_date
        ORDER BY target_date
    """).fetchall()
    for r in rows:
        print(f"Target Date: {r['target_date']} | Count: {r['cnt']}")
        
    # 4. Error/Warning count in logs (if logged in DB)
    # Check if there is a log table in the DB
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\nTables in DB: {tables}")
    
    conn.close()

def analyze_logs():
    print("\n=== LOG FILES ANALYSIS (May 27 ~ May 30) ===")
    dates = ["20260527", "20260528", "20260529", "20260530"]
    
    for d in dates:
        log_file = os.path.join(logs_dir, f"app_{d}.log")
        if not os.path.exists(log_file):
            print(f"\nLog file app_{d}.log does not exist.")
            continue
            
        size = os.path.getsize(log_file)
        print(f"\n--- Log: app_{d}.log ({size:,} bytes) ---")
        
        errors = 0
        warnings = 0
        waf_blocks = 0
        keys_exhausted = 0
        sse_publishes = 0
        crawler_completed_pages = 0
        poller_runs = 0
        
        # We will scan the log file and collect stats
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "ERROR" in line:
                    errors += 1
                if "WARNING" in line:
                    warnings += 1
                if "WAF 임시 차단" in line or "WAF" in line:
                    waf_blocks += 1
                if "All API keys are exhausted" in line or "키 소진" in line:
                    keys_exhausted += 1
                if "SSE 발행" in line or "SSE발행" in line:
                    sse_publishes += 1
                if "W" in line and "P" in line and "완료" in line: # e.g. [I2861 | e8efd] W9 ✅ P4/954 완료
                    crawler_completed_pages += 1
                if "[전략C] 폴링 시작" in line or "3중 폴링 시작" in line:
                    poller_runs += 1
                    
        print(f"  Errors: {errors} | Warnings: {warnings}")
        print(f"  WAF Blocks: {waf_blocks} | Keys Exhausted Events: {keys_exhausted}")
        print(f"  Crawler pages completed: {crawler_completed_pages}")
        print(f"  Poller runs: {poller_runs}")
        print(f"  SSE publishes: {sse_publishes}")
        
        # Show sample error or warnings if any
        if errors > 0 or warnings > 0:
            print("  [Sample Warnings/Errors (first 5)]:")
            printed = 0
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "ERROR" in line or "WARNING" in line:
                        # Skip recurring normal warnings if they clutter
                        print("    ", line.strip())
                        printed += 1
                        if printed >= 5:
                            break

if __name__ == "__main__":
    analyze_db()
    analyze_logs()
