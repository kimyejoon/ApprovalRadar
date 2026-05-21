import httpx
import json
import sys

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    url = "http://openapi.foodsafetykorea.go.kr/api/c79a5f07ff2543a19dbc/I2861/json/1/10/CHNG_DT=20260521"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, timeout=10)
        print("Status Code:", res.status_code)
        try:
            js = res.json()
            print(json.dumps(js, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Not JSON:", res.text[:500])

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
