"""페이지 스캔 히스토리(fingerprints/scan_times) 초기화"""
import sqlite3, json, sys
sys.stdout = sys.stdout if hasattr(sys.stdout, 'reconfigure') else sys.stdout

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\dist_release\food_safety.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT extra_state FROM crawler_state WHERE service_id = 'I2861'").fetchone()
if row:
    extra = json.loads(row["extra_state"] or "{}")
    fp_count = len(extra.get("page_fingerprints", {}))
    st_count = len(extra.get("page_scan_times", {}))
    print(f"Before: {fp_count} fingerprints, {st_count} scan_times")
    
    extra.pop("page_fingerprints", None)
    extra.pop("page_scan_times", None)
    # cursor_A_start, cursor_B_start도 리셋
    extra.pop("cursor_A_start", None)
    extra.pop("cursor_B_start", None)
    
    conn.execute(
        "UPDATE crawler_state SET extra_state = ? WHERE service_id = 'I2861'",
        (json.dumps(extra, ensure_ascii=False),)
    )
    conn.commit()
    print("DONE: fingerprints, scan_times, cursor positions cleared")
else:
    print("No I2861 state found")

conn.close()
