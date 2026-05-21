import httpx
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def test(url, name):
    async with httpx.AsyncClient() as client:
        res = await client.get(url, timeout=10)
        if res.status_code == 200:
            js = res.json()
            data = js.get("I2861", {})
            total_count = data.get("total_count", "N/A")
            rows = data.get("row", [])
            print(f"\n[{name}]")
            print(f"URL: {url}")
            print(f"Total Count: {total_count} | Rows count: {len(rows)}")
            if rows:
                print(f"First row CHNG_DT: {rows[0].get('CHNG_DT')} | BSSH_NM: {rows[0].get('BSSH_NM')}")
                print(f"Last row CHNG_DT: {rows[-1].get('CHNG_DT')} | BSSH_NM: {rows[-1].get('BSSH_NM')}")
        else:
            print(f"[{name}] HTTP Status: {res.status_code}")

async def main():
    key = "c79a5f07ff2543a19dbc"
    
    # 1. Plain query (No filter)
    await test(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1000", "Plain No Filter")
    
    # 2. SYS_SYNC=LIVE
    await test(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1000/SYS_SYNC=LIVE", "SYS_SYNC=LIVE")
    
    # 3. CHNG_DT=20260521
    await test(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1000/CHNG_DT=20260521", "CHNG_DT=Today")
    
    # 4. CHNG_DT=20260521 & SYS_SYNC=LIVE
    await test(f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2861/json/1/1000/CHNG_DT=20260521&SYS_SYNC=LIVE", "CHNG_DT=Today & SYS_SYNC=LIVE")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
