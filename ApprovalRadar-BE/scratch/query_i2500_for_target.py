import asyncio
import sys

# Add project root to python path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.foodsafety_api import ApiClient

async def main():
    async with ApiClient() as client:
        print("Querying I2500 for license 19810053045...")
        res = await client.fetch_data("I2500", 1, 10, LCNS_NO="19810053045")
        print("I2500 Response:")
        print(res)

if __name__ == "__main__":
    asyncio.run(main())
