import httpx
import sqlite3
import asyncio
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

# Fetch one working key
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
api_keys = [r[0] for r in rows]
conn.close()

async def find_valid_key():
    async with httpx.AsyncClient() as client:
        for key in api_keys:
            url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1/CHNG_DT=20260519"
            try:
                res = await client.get(url, timeout=5.0)
                if res.status_code == 200:
                    js = res.json()
                    i2861 = js.get("I2861", {})
                    result = i2861.get("RESULT", {})
                    code = result.get("CODE")
                    if code != "INFO-300":
                        return key
            except Exception:
                pass
    return None

async def test_tail_page(client, key, page_num):
    start = (page_num - 1) * 1000 + 1
    end = page_num * 1000
    
    url_plain = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{start}/{end}"
    url_sync = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{start}/{end}/SYS_SYNC=LIVE"
    
    # Fetch Plain
    res_plain = await client.get(url_plain, timeout=15)
    data_plain = res_plain.json().get("I2861", {}) if res_plain.status_code == 200 else {}
    rows_plain = data_plain.get("row", [])
    count_plain = data_plain.get("total_count", "N/A")
    
    # Fetch Sync
    res_sync = await client.get(url_sync, timeout=15)
    data_sync = res_sync.json().get("I2861", {}) if res_sync.status_code == 200 else {}
    rows_sync = data_sync.get("row", [])
    count_sync = data_sync.get("total_count", "N/A")
    
    print(f"\n--- Page {page_num} ({start} ~ {end}) ---")
    print(f"Plain | total_count field: {count_plain} | rows returned: {len(rows_plain)}")
    print(f"Sync  | total_count field: {count_sync} | rows returned: {len(rows_sync)}")
    
    if rows_plain:
        print(f"Plain last row: {rows_plain[-1].get('BSSH_NM')} ({rows_plain[-1].get('INDUTY_CD_NM')})")
    if rows_sync:
        print(f"Sync last row: {rows_sync[-1].get('BSSH_NM')} ({rows_sync[-1].get('INDUTY_CD_NM')})")

async def main():
    key = await find_valid_key()
    if not key:
        print("No valid key")
        return
        
    async with httpx.AsyncClient() as client:
        # Let's test page 952 and 953 and 954
        for p in [952, 953, 954]:
            await test_tail_page(client, key, p)

if __name__ == "__main__":
    asyncio.run(main())
