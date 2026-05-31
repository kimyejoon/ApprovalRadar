import sqlite3
import httpx
import asyncio
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

# 1. Search local DB for exact names
def search_local_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    targets = ["유가네 수유점", "우주횟집", "중독마라탕", "커피101스트릿", "미스터육회연어왕"]
    print("=== LOCAL DATABASE SEARCH ===")
    for name in targets:
        rows = cursor.execute("SELECT * FROM businesses WHERE business_name LIKE ?", (f"%{name}%",)).fetchall()
        print(f"\nTarget: {name} | Found {len(rows)} records in DB")
        for r in rows:
            print(f"  ID: {r['id']} | LCNS: {r['license_no']} | Name: {r['business_name']} | EventDate: {r['last_event_date']} | CollectedBy: {r['collected_by']} | CreatedAt: {r['created_at']}")
            
    conn.close()

# 2. Query Foodsafety API live
async def query_live_api():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
    keys = [r[0] for r in rows]
    conn.close()
    
    key = keys[1] # Use Travis key (f1282c86037d4d1a9819)
    targets = ["유가네 수유점", "우주횟집", "중독마라탕", "커피101스트릿", "미스터육회연어왕"]
    
    print("\n=== LIVE OPENAPI INQUIRY ===")
    async with httpx.AsyncClient() as client:
        for name in targets:
            print(f"\n--- Querying live for name: {name} ---")
            
            # Query I2861 (Change History)
            url_i2861 = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/20/BSSH_NM={name}&SYS_SYNC=LIVE_1"
            try:
                res = await client.get(url_i2861, timeout=30)
                if res.status_code == 200:
                    js = res.json()
                    i2861 = js.get("I2861", {})
                    total_count = i2861.get("total_count", "N/A")
                    rows_api = i2861.get("row", [])
                    print(f"  [I2861] total_count: {total_count} | rows count: {len(rows_api)}")
                    for r in rows_api:
                        print(f"    - BSSH_NM: {r.get('BSSH_NM')} | LCNS_NO: {r.get('LCNS_NO')} | CHNG_DT: {r.get('CHNG_DT')} | CHNG_PRVNS: {r.get('CHNG_PRVNS')} | ADDR: {r.get('SITE_ADDR')}")
                else:
                    print(f"  [I2861] Failed with status: {res.status_code}")
            except Exception as e:
                print(f"  [I2861] Error: {e}")
                
            # Query I2500 (Details)
            url_i2500 = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/20/BSSH_NM={name}&SYS_SYNC=LIVE_1"
            try:
                res = await client.get(url_i2500, timeout=30)
                if res.status_code == 200:
                    js = res.json()
                    i2500 = js.get("I2500", {})
                    total_count = i2500.get("total_count", "N/A")
                    rows_api = i2500.get("row", [])
                    print(f"  [I2500] total_count: {total_count} | rows count: {len(rows_api)}")
                    for r in rows_api:
                        print(f"    - BSSH_NM: {r.get('BSSH_NM')} | LCNS_NO: {r.get('LCNS_NO')} | PRMS_DT: {r.get('PRMS_DT')} | INDUTY: {r.get('INDUTY_CD_NM')} | ADDR: {r.get('ADDR')}")
                else:
                    print(f"  [I2500] Failed with status: {res.status_code}")
            except Exception as e:
                print(f"  [I2500] Error: {e}")

if __name__ == "__main__":
    search_local_db()
    asyncio.run(query_live_api())
