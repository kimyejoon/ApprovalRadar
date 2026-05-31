import httpx
import asyncio
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    key = "f1282c86037d4d1a9819"
    target_date = "20260525"
    
    async with httpx.AsyncClient() as client:
        # Request 1: Without cache buster (may hit gateway cache)
        url_cached = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/10/CHNG_DT={target_date}"
        t0 = time.time()
        res_cached = await client.get(url_cached, timeout=10)
        elapsed_cached = time.time() - t0
        
        # Request 2: With cache buster (forces live fetch)
        ts = int(time.time())
        url_live = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/10/CHNG_DT={target_date}&SYS_SYNC=LIVE_{ts}"
        t1 = time.time()
        res_live = await client.get(url_live, timeout=10)
        elapsed_live = time.time() - t1
        
        print("\n--- Request 1 (Without Cache Buster) ---")
        print("URL:", url_cached)
        print("Status:", res_cached.status_code)
        print("Time:", round(elapsed_cached, 2), "s")
        if res_cached.status_code == 200:
            js = res_cached.json()
            i2500 = js.get("I2500", {})
            total_count = i2500.get("total_count", "N/A")
            rows = i2500.get("row", [])
            print(f"total_count: {total_count} | rows count: {len(rows)}")
            if rows:
                print("First row LCNS_NO:", rows[0].get("LCNS_NO"), "BSSH_NM:", rows[0].get("BSSH_NM"))
        else:
            print("Response:", res_cached.text[:200])
        
        print("\n--- Request 2 (With Cache Buster) ---")
        print("URL:", url_live)
        print("Status:", res_live.status_code)
        print("Time:", round(elapsed_live, 2), "s")
        if res_live.status_code == 200:
            js = res_live.json()
            i2500 = js.get("I2500", {})
            total_count = i2500.get("total_count", "N/A")
            rows = i2500.get("row", [])
            print(f"total_count: {total_count} | rows count: {len(rows)}")
            if rows:
                print("First row LCNS_NO:", rows[0].get("LCNS_NO"), "BSSH_NM:", rows[0].get("BSSH_NM"))
        else:
            print("Response:", res_live.text[:200])

if __name__ == "__main__":
    asyncio.run(main())
