import httpx
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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
    key = "c79a5f07ff2543a19dbc"
    
    # We fetch using templated URLs
    url_plain = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{{start}}/{{end}}"
    url_sync = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{{start}}/{{end}}/SYS_SYNC=LIVE"
    url_chng = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{{start}}/{{end}}/CHNG_DT=20260521"
    url_chng_sync = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/{{start}}/{{end}}/CHNG_DT=20260521&SYS_SYNC=LIVE"
    
    print("Fetching Plain rows...")
    plain_rows = await fetch_rows(url_plain, "I2861")
    print(f"Fetched {len(plain_rows)} Plain rows.")
    
    print("Fetching SYS_SYNC=LIVE rows...")
    sync_rows = await fetch_rows(url_sync, "I2861")
    print(f"Fetched {len(sync_rows)} SYS_SYNC=LIVE rows.")
    
    print("Fetching CHNG_DT=Today rows...")
    chng_rows = await fetch_rows(url_chng, "I2861")
    print(f"Fetched {len(chng_rows)} CHNG_DT=Today rows.")
    
    print("Fetching CHNG_DT=Today & SYS_SYNC=LIVE rows...")
    chng_sync_rows = await fetch_rows(url_chng_sync, "I2861")
    print(f"Fetched {len(chng_sync_rows)} CHNG_DT=Today & SYS_SYNC=LIVE rows.")
    
    # Map to license numbers
    plain_map = {r['LCNS_NO']: r for r in plain_rows if 'LCNS_NO' in r}
    sync_map = {r['LCNS_NO']: r for r in sync_rows if 'LCNS_NO' in r}
    chng_map = {r['LCNS_NO']: r for r in chng_rows if 'LCNS_NO' in r}
    chng_sync_map = {r['LCNS_NO']: r for r in chng_sync_rows if 'LCNS_NO' in r}
    
    # 1. Extra rows in SYS_SYNC=LIVE compared to Plain
    extra_in_sync = set(sync_map.keys()) - set(plain_map.keys())
    print(f"\n[1] Extra rows in SYS_SYNC=LIVE vs Plain: {len(extra_in_sync)} rows")
    for lcns in sorted(list(extra_in_sync))[:10]:
        r = sync_map[lcns]
        print(f"  LCNS: {lcns} | BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')} | CHNG_PRVNS: {r.get('CHNG_PRVNS')}")
        
    # 2. Extra rows in Plain compared to SYS_SYNC=LIVE
    extra_in_plain = set(plain_map.keys()) - set(sync_map.keys())
    print(f"\n[2] Extra rows in Plain vs SYS_SYNC=LIVE: {len(extra_in_plain)} rows")
    for lcns in sorted(list(extra_in_plain))[:10]:
        r = plain_map[lcns]
        print(f"  LCNS: {lcns} | BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')}")

    # 3. Compare CHNG_DT=Today with Plain
    extra_in_chng = set(chng_map.keys()) - set(plain_map.keys())
    print(f"\n[3] Extra rows in CHNG_DT=Today vs Plain: {len(extra_in_chng)} rows")
    
    # 4. Compare CHNG_DT=Today & SYS_SYNC=LIVE with Plain
    extra_in_chng_sync = set(chng_sync_map.keys()) - set(plain_map.keys())
    print(f"\n[4] Extra rows in CHNG_DT=Today & SYS_SYNC=LIVE vs Plain: {len(extra_in_chng_sync)} rows")
    
    # 5. Let's see if any row in SYS_SYNC=LIVE has CHNG_DT == '20260521'
    today_in_sync = [r for r in sync_rows if r.get('CHNG_DT') == '20260521']
    print(f"\n[5] Rows with CHNG_DT='20260521' in SYS_SYNC=LIVE: {len(today_in_sync)} rows")
    for r in today_in_sync[:10]:
        print(f"  LCNS: {r.get('LCNS_NO')} | BSSH_NM: {r.get('BSSH_NM')} | CHNG_DT: {r.get('CHNG_DT')} | CHNG_PRVNS: {r.get('CHNG_PRVNS')}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
