import httpx
import sqlite3
import asyncio
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

# Fetch all working keys
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
api_keys = [r[0] for r in rows]
conn.close()

async def test_key(client, key):
    url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/5"
    try:
        res = await client.get(url, timeout=5.0)
        if res.status_code == 200:
            js = res.json()
            data = js.get("I2861", {})
            total_count = data.get("total_count", "N/A")
            rows = data.get("row", [])
            result = data.get("RESULT", {})
            if result.get("CODE") == "INFO-300":
                print(f"Key: {key[:6]}... | Exhausted (INFO-300)")
            else:
                first_nm = rows[0].get("BSSH_NM") if rows else "N/A"
                first_dt = rows[0].get("CHNG_DT") if rows else "N/A"
                print(f"Key: {key[:6]}... | Total Count: {total_count:5s} | First Row: {first_nm} ({first_dt})")
        else:
            print(f"Key: {key[:6]}... | HTTP {res.status_code}")
    except Exception as e:
        print(f"Key: {key[:6]}... | Error: {e}")

async def main():
    async with httpx.AsyncClient() as client:
        tasks = [test_key(client, key) for key in api_keys]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
