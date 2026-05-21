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

async def test_url(client: httpx.AsyncClient, api_key: str, name: str, url: str, service_id: str):
    try:
        res = await client.get(url, timeout=10.0)
        print(f"\n[{name}]")
        print(f"URL: {url}")
        print(f"Status: {res.status_code}")
        try:
            js = res.json()
            service_data = js.get(service_id, {})
            result = service_data.get("RESULT", {})
            total_count = service_data.get("total_count", "N/A")
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
        
    urls = [
        # I2861 with ONLY SYS_SYNC=LIVE as a path segment
        ("I2861 with ONLY SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/5/SYS_SYNC=LIVE", "I2861"),
        # I2500 with ONLY SYS_SYNC=LIVE as a path segment
        ("I2500 with ONLY SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/5/SYS_SYNC=LIVE", "I2500"),
    ]
    
    async with httpx.AsyncClient() as client:
        for name, url, service_id in urls:
            await test_url(client, api_key, name, url, service_id)

if __name__ == "__main__":
    asyncio.run(run_tests())
