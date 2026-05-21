import asyncio
import os
import sys

# Add ApprovalRadar-BE to sys.path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.foodsafety_api import ApiClient

async def test():
    async with ApiClient() as client:
        # Fetching I2500 for today (20260521)
        res = await client.fetch_data("I2500", 1, 5, CHNG_DT="20260521")
        print("\nTest Result:")
        print(f"Response Keys: {res.keys() if res else None}")
        if res and "I2500" in res:
            result = res["I2500"].get("RESULT", {})
            print(f"Result Code: {result.get('CODE')}, Msg: {result.get('MSG')}")
            print(f"Total Count: {res['I2500'].get('total_count')}")
            print(f"Rows count: {len(res['I2500'].get('row', []))}")

if __name__ == "__main__":
    asyncio.run(test())
