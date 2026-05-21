import httpx
import sqlite3
import asyncio
import os

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
        # Check Plain 1/1
        res = await client.get(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1")
        print("Plain 1/1:")
        print(res.json().get("I2861", {}).get("total_count"))
        
        # Check SYS_SYNC=LIVE 1/1
        res = await client.get(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1/SYS_SYNC=LIVE")
        print("SYS_SYNC=LIVE 1/1:")
        print(res.json().get("I2861", {}).get("total_count"))

if __name__ == "__main__":
    asyncio.run(main())
