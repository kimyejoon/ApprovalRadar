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

async def test_endpoint(client: httpx.AsyncClient, name: str, url: str, service_id: str):
    try:
        res = await client.get(url, timeout=10.0)
        print(f"\n========================================\n[{name}]")
        print(f"URL: {url}")
        print(f"HTTP Status: {res.status_code}")
        if res.status_code != 200:
            print(f"Response text: {res.text[:300]}")
            return
        
        try:
            js = res.json()
            data = js.get(service_id, {})
            result = data.get("RESULT", {})
            total_count = data.get("total_count", "N/A")
            rows = data.get("row", [])
            print(f"Result Code: {result.get('CODE')}")
            print(f"Result Msg: {result.get('MSG')}")
            print(f"Total Count: {total_count}")
            print(f"Rows Returned: {len(rows)}")
            if rows:
                print("First row sample:")
                first_row = rows[0]
                # Filter print to key fields for readability
                filtered_row = {k: first_row[k] for k in ["LCNS_NO", "BSSH_NM", "CHNG_DT", "CHNG_PRVNS", "SITE_ADDR"] if k in first_row}
                if not filtered_row:
                    filtered_row = first_row
                print(f"  {filtered_row}")
        except Exception as e:
            print(f"Failed to parse JSON: {e}")
            print(f"Raw Response: {res.text[:300]}")
    except Exception as e:
        print(f"Request failed: {e}")

async def run_investigation():
    api_key = await find_valid_key()
    if not api_key:
        print("No active API keys found")
        return
        
    print(f"Using API Key: {api_key}")
    
    # Target dates
    past_date = "20260519"
    today_date = "20260521"
    
    # We will test both services I2861 and I2500 with different variations
    async with httpx.AsyncClient() as client:
        
        # --- I2861 Tests ---
        i2861_urls = [
            ("I2861 Plain No Params", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/10", "I2861"),
            ("I2861 ONLY SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/10/SYS_SYNC=LIVE", "I2861"),
            ("I2861 CHNG_DT=Past (Plain)", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/10/CHNG_DT={past_date}", "I2861"),
            ("I2861 CHNG_DT=Past & SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/10/CHNG_DT={past_date}&SYS_SYNC=LIVE", "I2861"),
            ("I2861 CHNG_DT=Today (Plain)", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/10/CHNG_DT={today_date}", "I2861"),
            ("I2861 CHNG_DT=Today & SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2861/json/1/10/CHNG_DT={today_date}&SYS_SYNC=LIVE", "I2861"),
        ]
        
        print("\n🔎 INVESTIGATING I2861 (음식점업소 인허가변경정보)")
        for name, url, service_id in i2861_urls:
            await test_endpoint(client, name, url, service_id)
            
        # --- I2500 Tests ---
        i2500_urls = [
            ("I2500 Plain No Params", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/10", "I2500"),
            ("I2500 ONLY SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/10/SYS_SYNC=LIVE", "I2500"),
            ("I2500 CHNG_DT=Past (Plain)", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/10/CHNG_DT={past_date}", "I2500"),
            ("I2500 CHNG_DT=Past & SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/10/CHNG_DT={past_date}&SYS_SYNC=LIVE", "I2500"),
            ("I2500 CHNG_DT=Today (Plain)", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/10/CHNG_DT={today_date}", "I2500"),
            ("I2500 CHNG_DT=Today & SYS_SYNC=LIVE", f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/I2500/json/1/10/CHNG_DT={today_date}&SYS_SYNC=LIVE", "I2500"),
        ]
        
        print("\n🔎 INVESTIGATING I2500 (식품 인허가 상세정보)")
        for name, url, service_id in i2500_urls:
            await test_endpoint(client, name, url, service_id)

if __name__ == "__main__":
    asyncio.run(run_investigation())
