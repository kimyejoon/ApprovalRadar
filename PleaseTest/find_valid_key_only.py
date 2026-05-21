import httpx
import sqlite3
import asyncio
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
api_keys = [r[0] for r in rows]
conn.close()

async def check_key(client, key):
    url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1/CHNG_DT=20260519"
    try:
        res = await client.get(url, timeout=5.0)
        if res.status_code == 200:
            js = res.json()
            code = js.get("I2861", {}).get("RESULT", {}).get("CODE")
            msg = js.get("I2861", {}).get("RESULT", {}).get("MSG")
            return key, code, msg
    except Exception as e:
        return key, "ERROR", str(e)
    return key, "UNKNOWN", "No response"

async def main():
    async with httpx.AsyncClient() as client:
        tasks = [check_key(client, k) for k in api_keys]
        results = await asyncio.gather(*tasks)
        
        valid_keys = []
        print("=== Key Status Check ===")
        for key, code, msg in results:
            print(f"Key: {key[:10]}... | Code: {code} | Msg: {msg}")
            if code not in ["INFO-300", "INFO-333", "ERROR", "UNKNOWN"]:
                valid_keys.append(key)
        
        print(f"\nTotal valid keys: {len(valid_keys)}")
        if valid_keys:
            print(f"First valid key: {valid_keys[0]}")

if __name__ == "__main__":
    asyncio.run(main())
