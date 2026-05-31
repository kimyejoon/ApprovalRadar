import httpx
import asyncio
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    key = "f1282c86037d4d1a9819"
    dates = ["20260527", "20260528", "20260529", "20260530"]
    targets = {
        "19810053045": "유가네 수유점",
        "20060114564": "우주횟집",
        "20000358305": "중독마라탕",
        "20200300646": "커피101스트릿(옥길점)",
        "20110313244": "미스터육회연어왕 안산점"
    }
    
    async with httpx.AsyncClient() as client:
        for d in dates:
            print(f"\n--- Checking I2500 with CHNG_DT={d} ---")
            page = 1
            max_pages = 5
            found_count = 0
            
            while page <= max_pages:
                start = (page - 1) * 1000 + 1
                end = page * 1000
                # Use cache buster
                url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/{start}/{end}/CHNG_DT={d}&SYS_SYNC=LIVE_123"
                try:
                    res = await client.get(url, timeout=30)
                    if res.status_code == 200:
                        js = res.json()
                        rows = js.get("I2500", {}).get("row", [])
                        if not rows:
                            break
                            
                        # Search for our targets in the rows
                        for r in rows:
                            lcns = r.get("LCNS_NO")
                            if lcns in targets:
                                print(f"  [FOUND] Date: {d} | Page: {page} | Name: {targets[lcns]} | LCNS: {lcns} | ADDR: {r.get('ADDR')}")
                                found_count += 1
                        
                        page += 1
                    else:
                        print(f"  Failed with status: {res.status_code}")
                        break
                except Exception as e:
                    print(f"  Error: {e}")
                    break
            
            print(f"  Search for Date {d} completed. Found {found_count} targets.")

if __name__ == "__main__":
    asyncio.run(main())
