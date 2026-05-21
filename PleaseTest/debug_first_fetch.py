import httpx
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    url = "http://openapi.foodsafetykorea.go.kr/api/c79a5f07ff2543a19dbc/I2861/json/1/1000"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, timeout=15)
        print("Status Code:", res.status_code)
        try:
            js = res.json()
            data = js.get("I2861", {})
            print("Keys:", data.keys())
            print("Result:", data.get("RESULT"))
            print("Total Count:", data.get("total_count"))
            print("Rows count:", len(data.get("row", [])))
        except Exception as e:
            print("Exception:", e)
            print("Text:", res.text[:300])

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
