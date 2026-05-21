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

async def test_url(client: httpx.AsyncClient, api_key: str, name: str, url: str):
    try:
        res = await client.get(url, timeout=10.0)
        print(f"\n[{name}]")
        print(f"URL: {url}")
        print(f"Status: {res.status_code}")
        try:
            js = res.json()
            i2861 = js.get("I2861", {})
            result = i2861.get("RESULT", {})
            total_count = i2861.get("total_count", "N/A")
            print(f"Result Code: {result.get('CODE')}, Msg: {result.get('MSG')}, Total Count: {total_count}")
        except Exception:
            print(f"Content (Not JSON): {res.text[:200]}")
    except Exception as e:
        print(f"[{name}] Request failed: {e}")

async def run_tests():
    api_key = await find_valid_key()
    if not api_key:
        print("Could not find any active API key with remaining quota")
        return
        
    today_str = "20260521"
    
    # We are testing I2861!
    urls = {
        "1. Plain Query (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/5/CHNG_DT={today_str}",
        "2. SYS_SYNC=LIVE (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/5/CHNG_DT={today_str}/SYS_SYNC=LIVE",
        "3. Random Dummy Param (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/5/CHNG_DT={today_str}/dummy=123",
        "4. Plain Slash End (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/5/CHNG_DT={today_str}/",
    }
    
    async with httpx.AsyncClient() as client:
        for name, url in urls.items():
            await test_url(client, api_key, name, url)

if __name__ == "__main__":
    asyncio.run(run_tests())
