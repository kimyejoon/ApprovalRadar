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

# Fetch all keys
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
api_keys = [r[0] for r in rows]
conn.close()

async def find_valid_key():
    today_str = "20260521"
    async with httpx.AsyncClient() as client:
        for key in api_keys:
            # test plain query with past date 20260519 to avoid 19:00 block, just to see if key works (not INFO-300)
            url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/1/CHNG_DT=20260519"
            try:
                res = await client.get(url, timeout=5.0)
                if res.status_code == 200:
                    js = res.json()
                    i2500 = js.get("I2500", {})
                    result = i2500.get("RESULT", {})
                    code = result.get("CODE")
                    if code != "INFO-300":
                        print(f"Found valid key: {key[:6]}... (Code: {code}, Msg: {result.get('MSG')})")
                        return key
                    else:
                        # Exceeded
                        pass
            except Exception as e:
                pass
    return None

async def test_url(client: httpx.AsyncClient, api_key: str, name: str, url_template: str):
    url = url_template.format(api_key=api_key)
    try:
        res = await client.get(url, timeout=10.0)
        print(f"\n[{name}]")
        print(f"URL: {url}")
        print(f"Status: {res.status_code}")
        try:
            js = res.json()
            i2500 = js.get("I2500", {})
            result = i2500.get("RESULT", {})
            total_count = i2500.get("total_count", "N/A")
            print(f"Result Code: {result.get('CODE')}, Msg: {result.get('MSG')}, Total Count: {total_count}")
            if total_count != "N/A" and total_count.strip() and int(total_count) > 0:
                print(f"Sample row: {i2500.get('row', [])[:1]}")
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
    
    # Let's test various combinations for today 20260521
    # Note that plain query should return INFO-700 because today is May 21 and it's before 19:00 (relative to OpenAPI data release)
    # Wait, let's see if plain query returns INFO-700 or success, or what.
    urls = {
        "1. Plain Query (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{{api_key}}/I2500/json/1/5/CHNG_DT={today_str}",
        "2. SYS_SYNC=LIVE (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{{api_key}}/I2500/json/1/5/CHNG_DT={today_str}/SYS_SYNC=LIVE",
        "3. SYS_SYNC=LIVE in parameters (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{{api_key}}/I2500/json/1/5/SYS_SYNC=LIVE/CHNG_DT={today_str}",
        "4. DUMMY=1 (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{{api_key}}/I2500/json/1/5/CHNG_DT={today_str}/DUMMY=1",
        "5. DUMMY=1 in parameters (Today)": f"http://openapi.foodsafetykorea.go.kr/api/{{api_key}}/I2500/json/1/5/DUMMY=1/CHNG_DT={today_str}",
    }
    
    async with httpx.AsyncClient() as client:
        for name, url_template in urls.items():
            await test_url(client, api_key, name, url_template)

if __name__ == "__main__":
    asyncio.run(run_tests())
