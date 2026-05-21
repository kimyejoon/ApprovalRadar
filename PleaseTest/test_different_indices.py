import httpx
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    async with httpx.AsyncClient() as client:
        for end in [5, 10, 20, 50, 100, 1000]:
            url = f"http://openapi.foodsafetykorea.go.kr/api/c79a5f07ff2543a19dbc/I2861/json/1/{end}/CHNG_DT=20260521"
            res = await client.get(url, timeout=10)
            if res.status_code == 200:
                js = res.json()
                data = js.get("I2861", {})
                total_count = data.get("total_count", "N/A")
                rows = len(data.get("row", []))
                print(f"End Index: {end:4d} | Total Count: {total_count:5s} | Rows Returned: {rows:4d}")
            else:
                print(f"End Index: {end:4d} | HTTP Status: {res.status_code}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
