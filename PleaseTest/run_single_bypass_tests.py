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
        # Test I2861 with single slash bypass
        url_i2861_bypass = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/5/SYS_SYNC=LIVE"
        res_i2861 = await client.get(url_i2861_bypass, timeout=10.0)
        print("I2861 bypass status:", res_i2861.status_code)
        print("I2861 bypass response text:", res_i2861.text[:200])
        
        # Test I2500 with single slash bypass
        url_i2500_bypass = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/5/SYS_SYNC=LIVE"
        res_i2500 = await client.get(url_i2500_bypass, timeout=10.0)
        print("I2500 bypass status:", res_i2500.status_code)
        print("I2500 bypass response text:", res_i2500.text[:200])

if __name__ == "__main__":
    asyncio.run(main())
