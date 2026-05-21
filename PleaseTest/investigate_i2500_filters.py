import httpx
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    key = "c79a5f07ff2543a19dbc"
    async with httpx.AsyncClient() as client:
        # Check I2500 total count behavior
        for end in [5, 10, 50, 100, 500]:
            url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/{end}"
            res = await client.get(url, timeout=10)
            if res.status_code == 200:
                js = res.json()
                data = js.get("I2500", {})
                total_count = data.get("total_count", "N/A")
                rows = len(data.get("row", []))
                print(f"I2500 No Filter | End Index: {end:4d} | Total Count: {total_count:5s} | Rows: {rows:4d}")
            else:
                print(f"I2500 No Filter | End Index: {end:4d} | Status: {res.status_code}")
                
        # Check I2500 with CHNG_DT
        for end in [5, 10, 50, 100, 500]:
            url = f"http://openapi.foodsafetykorea.go.kr/api/{key}/I2500/json/1/{end}/CHNG_DT=20260521"
            res = await client.get(url, timeout=10)
            if res.status_code == 200:
                js = res.json()
                data = js.get("I2500", {})
                total_count = data.get("total_count", "N/A")
                rows = len(data.get("row", []))
                print(f"I2500 CHNG_DT=Today | End Index: {end:4d} | Total Count: {total_count:5s} | Rows: {rows:4d}")
            else:
                print(f"I2500 CHNG_DT=Today | End Index: {end:4d} | Status: {res.status_code}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
