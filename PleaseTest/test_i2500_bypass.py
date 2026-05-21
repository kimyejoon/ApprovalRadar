import sqlite3
import httpx
import asyncio
import os
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

if not os.path.exists(db_path):
    print("Database not found")
    sys.exit(1)

# Fetch one active api key
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
row = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1 LIMIT 1").fetchone()
if not row:
    print("No active API keys found in DB")
    sys.exit(1)
api_key = row[0]
conn.close()

print(f"Using API Key: {api_key[:6]}...")

async def test_url(client: httpx.AsyncClient, name: str, url: str):
    try:
        res = await client.get(url, timeout=10.0)
        print(f"\n[{name}]")
        print(f"URL: {url}")
        print(f"Status: {res.status_code}")
        try:
            js = res.json()
            # print code and total_count or msg
            i2500 = js.get("I2500", {})
            result = i2500.get("RESULT", {})
            total_count = i2500.get("total_count", "N/A")
            print(f"Result Code: {result.get('CODE')}, Msg: {result.get('MSG')}, Total Count: {total_count}")
            if total_count != "N/A" and int(total_count) > 0:
                print(f"Sample row: {i2500.get('row', [])[:1]}")
        except Exception:
            print(f"Content (Not JSON): {res.text[:200]}")
    except Exception as e:
        print(f"[{name}] Request failed: {e}")

async def run_tests():
    # 20260521 is today's date
    today_str = "20260521"
    
    urls = {
        "1. Plain Query": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/5/CHNG_DT={today_str}",
        "2. SYS_SYNC=LIVE": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/5/CHNG_DT={today_str}/SYS_SYNC=LIVE",
        "3. SYS_SYNC=L": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/5/CHNG_DT={today_str}/SYS_SYNC=L",
        "4. Random Dummy Param": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/5/CHNG_DT={today_str}/DUMMY_KEY=DUMMY_VAL",
        "5. Plain Slash End": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/5/CHNG_DT={today_str}/",
    }
    
    async with httpx.AsyncClient() as client:
        for name, url in urls.items():
            await test_url(client, name, url)

if __name__ == "__main__":
    asyncio.run(run_tests())
