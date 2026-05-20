import asyncio

def run_sync():
    print("수동으로 차분 동기화(Delta Sync)를 1회 실행합니다...")
    from scraper import run_all_scrapers
    asyncio.run(run_all_scrapers())
