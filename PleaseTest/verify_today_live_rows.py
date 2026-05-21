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

async def main():
    key = await find_valid_key()
    if not key:
        print("No valid key")
        return
        
    async with httpx.AsyncClient() as client:
        # Fetch I2861 with SYS_SYNC=LIVE
        res = await client.get(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1000/SYS_SYNC=LIVE")
        if res.status_code == 200:
            js = res.json()
            rows = js.get("I2861", {}).get("row", [])
            print(f"Total rows fetched: {len(rows)}")
            today_rows = [r for r in rows if r.get("CHNG_DT") == "20260521"]
            print(f"Number of rows with CHNG_DT='20260521' in response: {len(today_rows)}")
            for idx, r in enumerate(today_rows[:10]):
                print(f"  {idx+1}: {r.get('BSSH_NM')} | {r.get('LCNS_NO')} | CHNG_DT: {r.get('CHNG_DT')}")
        else:
            print("Failed to fetch:", res.status_code)

if __name__ == "__main__":
    asyncio.run(main())
