import sqlite3
import re

DB_FILE = "food_safety.db"

def classify_update_type():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT license_no, prev_business_name FROM businesses WHERE update_type = '변경민원';")
    rows = cursor.fetchall()

    update_queries = []
    
    # Address regex: Starts with regional name, followed by space, and typically ends with numbers/동/로/길 etc.
    # We will use a combination of \n check and specific address pattern.
    addr_pattern = re.compile(r'^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|강원도|충청북도|충북|충청남도|충남|전라북도|전북|전라남도|전남|경상북도|경북|경상남도|경남|제주특별자치도|제주)\s+[가-힣]+(시|군|구|읍|면|동|로|길)\s+')

    for license_no, prev_name in rows:
        if not prev_name:
            continue
            
        infer_detail = prev_name
        # 1. Check if it's a name (contains asterisks)
        if '*' in prev_name:
            infer_type = "변경민원-성함"
        # 2. Check if it's an address
        elif '\n' in prev_name or addr_pattern.match(prev_name):
            infer_type = "변경민원-주소"
        # 3. Otherwise, treat as business name
        else:
            infer_type = "변경민원-상호명"
            
        update_queries.append((infer_type, infer_detail, license_no))

    # Perform updates for 변경민원
    cursor.executemany("UPDATE businesses SET infer_update_type = ?, infer_update_detail = ? WHERE license_no = ?", update_queries)
    
    # Add logic for update_type IS NULL
    cursor.execute("UPDATE businesses SET infer_update_type = '신규등록' WHERE update_type IS NULL AND license_date = last_event_date;")
    new_reg_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"Successfully updated {len(update_queries)} records for '변경민원'.")
    print(f"Successfully updated {new_reg_count} records for '신규등록' (update_type IS NULL).")

if __name__ == "__main__":
    classify_update_type()
