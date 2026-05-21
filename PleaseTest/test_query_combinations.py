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

async def run_test(client, key, name, query_part):
    url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/10/{query_part}"
    try:
        res = await client.get(url, timeout=10.0)
        if res.status_code == 200:
            js = res.json()
            data = js.get("I2861", {})
            total_count = data.get("total_count", "N/A")
            rows = data.get("row", [])
            code = data.get("RESULT", {}).get("CODE")
            msg = data.get("RESULT", {}).get("MSG")
            
            first_nm = rows[0].get("BSSH_NM") if rows else "N/A"
            first_dt = rows[0].get("CHNG_DT") if rows else "N/A"
            print(f"[{name}] Code: {code} | Total: {total_count:5s} | First Row: {first_nm} ({first_dt})")
        else:
            print(f"[{name}] HTTP {res.status_code}")
    except Exception as e:
        print(f"[{name}] Error: {e}")

async def main():
    key = await find_valid_key()
    if not key:
        print("No valid key")
        return
    print(f"Testing with key: {key[:6]}...\n")
    
    async with httpx.AsyncClient() as client:
        # Test basic cases
        await run_test(client, key, "1. No params", "")
        await run_test(client, key, "2. ONLY SYS_SYNC=LIVE", "SYS_SYNC=LIVE")
        
        # Test 20260519
        await run_test(client, key, "3. CHNG_DT=20260519", "CHNG_DT=20260519")
        await run_test(client, key, "4. CHNG_DT=20260519 & SYS_SYNC=LIVE", "CHNG_DT=20260519&SYS_SYNC=LIVE")
        
        # Test 20260520
        await run_test(client, key, "5. CHNG_DT=20260520", "CHNG_DT=20260520")
        await run_test(client, key, "6. CHNG_DT=20260520 & SYS_SYNC=LIVE", "CHNG_DT=20260520&SYS_SYNC=LIVE")
        
        # Test 20260521 (Today)
        await run_test(client, key, "7. CHNG_DT=20260521", "CHNG_DT=20260521")
        await run_test(client, key, "8. CHNG_DT=20260521 & SYS_SYNC=LIVE", "CHNG_DT=20260521&SYS_SYNC=LIVE")

if __name__ == "__main__":
    asyncio.run(main())
