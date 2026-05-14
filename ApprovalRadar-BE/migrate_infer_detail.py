import sqlite3
import re
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "food_safety.db")

def migrate():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT license_no, infer_update_type FROM businesses WHERE infer_update_type IS NOT NULL")
    rows = cursor.fetchall()

    updates = []
    
    for license_no, infer_val in rows:
        if not infer_val:
            continue
            
        new_type = infer_val
        new_detail = None
        
        if infer_val == "변경민원(지위승계 : 양도.양수)":
            new_type = "대표자변경"
            new_detail = "지위승계(양도.양수)"
        elif infer_val.startswith("대표자변경:[") and infer_val.endswith("]"):
            new_type = "대표자변경"
            new_detail = infer_val[7:-1]
        elif infer_val.startswith("명칭변경:[") and infer_val.endswith("]"):
            new_type = "명칭변경"
            new_detail = infer_val[6:-1]
        elif infer_val.startswith("상태변경:[") and infer_val.endswith("]"):
            new_type = "상태변경"
            new_detail = infer_val[6:-1]
        elif infer_val.startswith("상태변경:"):
            new_type = "상태변경"
            new_detail = infer_val[5:]
        elif infer_val.startswith("변경민원-상호명:"):
            new_type = "변경민원-상호명"
            new_detail = infer_val[9:]
        elif infer_val.startswith("변경민원-주소:"):
            new_type = "변경민원-주소"
            new_detail = infer_val[8:]
        elif infer_val.startswith("변경민원-성함:"):
            new_type = "변경민원-성함"
            new_detail = infer_val[8:]
        elif infer_val == "신규등록" or infer_val == "초기수집(과거변경있음)":
            new_type = infer_val
            new_detail = None
        else:
            # Check if there's any other pattern
            if ":" in infer_val and not infer_val.endswith("]"):
                parts = infer_val.split(":", 1)
                new_type = parts[0]
                new_detail = parts[1]
                
        updates.append((new_type, new_detail, license_no))

    cursor.executemany("UPDATE businesses SET infer_update_type = ?, infer_update_detail = ? WHERE license_no = ?", updates)
    conn.commit()
    conn.close()
    
    print(f"Migration completed for {len(updates)} records.")

if __name__ == "__main__":
    migrate()
