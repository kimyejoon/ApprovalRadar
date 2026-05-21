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

async def fetch_rows(url_template, service_id):
    all_rows = []
    async with httpx.AsyncClient() as client:
        for page in range(5): # Fetch up to 5000 rows
            start = page * 1000 + 1
            end = (page + 1) * 1000
            url = url_template.format(start=start, end=end)
            try:
                res = await client.get(url, timeout=20.0)
                if res.status_code == 200:
                    js = res.json()
                    data = js.get(service_id, {})
                    rows = data.get("row", [])
                    result = data.get("RESULT", {})
                    if result.get("CODE") == "INFO-300":
                        print(f"Key exhausted during fetch at page {page}")
                        break
                    if not rows:
                        break
                    all_rows.extend(rows)
                    if len(rows) < 1000:
                        break
                else:
                    print(f"Failed to fetch {url}: {res.status_code}")
                    break
            except Exception as e:
                print(f"Exception fetching {url}: {e}")
                break
    return all_rows

async def main():
    key = await find_valid_key()
    if not key:
        print("No active API keys with remaining quota found.")
        return
    print(f"Using working key: {key}")
    
    # We fetch using templated URLs
    url_plain = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{{start}}/{{end}}"
    url_sync = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{{start}}/{{end}}/SYS_SYNC=LIVE"
    
    print("Fetching Plain rows...")
    plain_rows = await fetch_rows(url_plain, "I2861")
    print(f"Fetched {len(plain_rows)} Plain rows.")
    
    print("Fetching SYS_SYNC=LIVE rows...")
    sync_rows = await fetch_rows(url_sync, "I2861")
    print(f"Fetched {len(sync_rows)} SYS_SYNC=LIVE rows.")
    
    # Map to license numbers
    plain_map = {r['LCNS_NO']: r for r in plain_rows if 'LCNS_NO' in r}
    sync_map = {r['LCNS_NO']: r for r in sync_rows if 'LCNS_NO' in r}
    
    # 1. Extra rows in SYS_SYNC=LIVE compared to Plain
    extra_in_sync = set(sync_map.keys()) - set(plain_map.keys())
    print(f"\n[1] Extra rows in SYS_SYNC=LIVE vs Plain: {len(extra_in_sync)} rows")
    for lcns in sorted(list(extra_in_sync)):
        r = sync_map[lcns]
        print(f"  LCNS: {lcns} | BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')} | CHNG_PRVNS: {r.get('CHNG_PRVNS')}")
        
    # 2. Extra rows in Plain compared to SYS_SYNC=LIVE
    extra_in_plain = set(plain_map.keys()) - set(sync_map.keys())
    print(f"\n[2] Extra rows in Plain vs SYS_SYNC=LIVE: {len(extra_in_plain)} rows")
    for lcns in sorted(list(extra_in_plain)):
        r = plain_map[lcns]
        print(f"  LCNS: {lcns} | BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')}")

if __name__ == "__main__":
    asyncio.run(main())
