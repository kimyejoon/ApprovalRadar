import httpx
import sqlite3
import asyncio
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

async def test_i2500():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    rows = cursor.execute("SELECT key_value FROM api_keys WHERE is_active = 1").fetchall()
    keys = [r[0] for r in rows]
    conn.close()
    
    # Find a valid key
    valid_key = None
    async with httpx.AsyncClient() as client:
        for k in keys:
            url = f"http://openapi.foodsafetykorea.go.kr/api/{k}/I2500/json/1/1"
            try:
                res = await client.get(url, timeout=5)
                js = res.json()
                if js.get("I2500", {}).get("RESULT", {}).get("CODE") != "INFO-300":
                    valid_key = k
                    break
            except Exception:
                pass
                
    if not valid_key:
        print("No valid key found")
        return
        
    print(f"Using key: {valid_key[:6]}...")
    target_date = "20260525"
    
    async with httpx.AsyncClient() as client:
        # Request 1: Without cache buster (may hit gateway cache)
        url_cached = f"http://openapi.foodsafetykorea.go.kr/api/{valid_key}/I2500/json/1/10/CHNG_DT={target_date}"
        t0 = time.time()
        res_cached = await client.get(url_cached, timeout=10)
        elapsed_cached = time.time() - t0
        
        # Request 2: With cache buster (forces live fetch)
        ts = int(time.time())
        url_live = f"http://openapi.foodsafetykorea.go.kr/api/{valid_key}/I2500/json/1/10/CHNG_DT={target_date}&SYS_SYNC=LIVE_{ts}"
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

if __name__ == "__main__":
    asyncio.run(test_i2500())
