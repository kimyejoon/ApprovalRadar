import asyncio
import sys
import datetime

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from scraper import run_scraper_for_service_with_rows

async def main():
    today = datetime.datetime.now().strftime("%Y%m%d")
    
    # Unique License number for testing
    lcns_no = f"TEST_NEW_{datetime.datetime.now().strftime('%H%M%S')}"
    
    mock_row = {
        "LCNS_NO": lcns_no,
        "BSSH_NM": "테스트 신규 치킨집",
        "ADDR": "서울특별시 강남구 테헤란로 123",
        "PRSDNT_NM": "홍길동",
        "BSN_STATE_NM": "영업/정상",
        "PRMS_DT": today,
        "TELNO": "02-1234-5678",
        "INDUTY_CD_NM": "일반음식점",
        "CHNG_DT": today,
        "raw_row": {}  # to avoid issues if nested raw_row is saved
    }
    
    # We pass it as raw_row key as well just in case run_scraper_for_service_with_rows expects it
    mock_row["raw_row"] = mock_row.copy()
    
    print(f"Inserting mock new registration row: LCNS_NO={lcns_no}, PRMS_DT={today}")
    
    # Run the scraper with mock row
    await run_scraper_for_service_with_rows("I2500", [mock_row], collected_by="chng_dt_poller")
    
    print("Insertion completed! Checking database to confirm...")
    
    import sqlite3
    db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    row = cursor.execute(
        "SELECT * FROM businesses WHERE license_no = ?", (lcns_no,)
    ).fetchone()
    
    if row:
        print(f"Record found in DB!")
        print(f"  License No: {row['license_no']}")
        print(f"  Business Name: {row['business_name']}")
        print(f"  License Date: {row['license_date']}")
        print(f"  Last Event Date: {row['last_event_date']}")
        print(f"  Infer Update Type: {row['infer_update_type']}")
        print(f"  Infer Update Detail: {row['infer_update_detail']}")
    else:
        print("Record NOT found in DB!")
        
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
