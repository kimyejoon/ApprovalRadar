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

async def test_date(client, key, label, date_str):
    url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/15/CHNG_DT={date_str}"
    res = await client.get(url, timeout=10)
    rows = res.json().get("I2861", {}).get("row", []) if res.status_code == 200 else []
    print(f"\n=== {label} (CHNG_DT={date_str}) ===")
    print(f"Rows returned: {len(rows)}")
    for idx, r in enumerate(rows[:5]):
        print(f"  {idx+1}: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')} | LCNS: {r.get('LCNS_NO')}")

async def main():
    key = await find_valid_key()
    if not key:
        print("No valid key")
        return
        
    async with httpx.AsyncClient() as client:
        await test_date(client, key, "Today", "20260521")
        await test_date(client, key, "Yesterday", "20260520")
        await test_date(client, key, "2 Days Ago", "20260519")

if __name__ == "__main__":
    asyncio.run(main())
