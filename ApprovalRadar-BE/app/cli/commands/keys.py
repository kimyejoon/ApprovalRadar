import asyncio
from app.clients.foodsafety_api import ApiClient

def check_keys():
    print("API 키 상태를 점검합니다...")
    async def _run():
        async with ApiClient() as client:
            await client.check_keys_status()
    asyncio.run(_run())
