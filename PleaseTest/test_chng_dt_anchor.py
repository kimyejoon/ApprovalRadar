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

async def test_date(client, key, date_str):
    url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/10/CHNG_DT={date_str}"
    url_sync = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/10/CHNG_DT={date_str}&SYS_SYNC=LIVE"
    
    res = await client.get(url, timeout=10)
    data = res.json().get("I2861", {}) if res.status_code == 200 else {}
    rows = data.get("row", [])
    count = data.get("total_count", "N/A")
    
    res_sync = await client.get(url_sync, timeout=10)
    data_sync = res_sync.json().get("I2861", {}) if res_sync.status_code == 200 else {}
    rows_sync = data_sync.get("row", [])
    count_sync = data_sync.get("total_count", "N/A")
    
    print(f"\n[CHNG_DT={date_str}]")
    print(f"Plain | total_count field: {count:5s} | rows: {len(rows)}")
    if rows:
        print(f"  Plain first row CHNG_DT: {rows[0].get('CHNG_DT')} | BSSH_NM: {rows[0].get('BSSH_NM')}")
    print(f"Sync  | total_count field: {count_sync:5s} | rows: {len(rows_sync)}")
    if rows_sync:
        print(f"  Sync first row CHNG_DT:  {rows_sync[0].get('CHNG_DT')} | BSSH_NM: {rows_sync[0].get('BSSH_NM')}")

async def main():
    key = await find_valid_key()
    if not key:
        print("No valid key")
        return
        
    async with httpx.AsyncClient() as client:
        dates = [
            "20260521",
            "20260520",
            "20260519",
            "20260515",
            "20260501",
            "20260401",
            "20250101"
        ]
        for d in dates:
            await test_date(client, key, d)

if __name__ == "__main__":
    asyncio.run(main())
