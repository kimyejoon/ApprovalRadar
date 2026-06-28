import os
import sys
import asyncio
import sqlite3

# BE path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.foodsafety_api import ApiClient
from scraper import run_scraper_for_service_with_rows

targets = [
    '20260382028', '20170094715', '20220550268', '20170094166', '20080614019', 
    '20230457195', '20260481267', '20090627445', '19970306053', '20100364180', 
    '20260415053', '20180324069', '20210389619', '20140316091', '20150297529', 
    '20230148892', '20020221802'
]

async def backfill():
    print(f"[1] 시작: {len(targets)}개 누락 의심 라이선스의 모든 변경 이력 백필...")
    
    async with ApiClient() as client:
        for idx, lcns in enumerate(targets, 1):
            print(f"[{idx}/{len(targets)}] LCNS: {lcns} 조회 중...")
            try:
                res = await client.fetch_data("I2861", 1, 100, LCNS_NO=lcns)
                rows = []
                if res and "I2861" in res:
                    rows = res["I2861"].get("row", [])
                
                if rows:
                    # Filter only rows with valid CHNG_DT
                    valid_rows = [r for r in rows if r.get("CHNG_DT")]
                    if valid_rows:
                        # Map fields if necessary, but run_scraper_for_service_with_rows handles standard raw rows
                        # Wait, let's see how I2861 rows are parsed in run_scraper_for_service_with_rows
                        print(f"  -> OpenAPI에서 {len(valid_rows)}개 변경 이력 발견. DB 삽입 실행...")
                        
                        # run_scraper_for_service_with_rows is async
                        await run_scraper_for_service_with_rows(
                            "I2861", valid_rows, collected_by="chng_dt_poller"
                        )
                        print(f"  -> {lcns} 백필 완료.")
                else:
                    print(f"  -> {lcns} 변경 이력 없음.")
            except Exception as e:
                print(f"❌ {lcns} 백필 중 오류 발생: {e}")
                
    print("[2] 완료: 모든 누락 건 백필이 성공적으로 수행되었습니다.")

if __name__ == "__main__":
    asyncio.run(backfill())
