"""937,000~953,000 범위에서 CHNG_DT=20260519 존재 여부 즉시 확인"""
import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime
from app.clients.foodsafety_api import ApiClient

TODAY = datetime.now().strftime("%Y%m%d")
SVC = "I2861"

async def main():
    async with ApiClient() as client:
        today_found = []
        total = 0
        
        # 937,000부터 953,000까지 1000건씩 스캔
        for start in range(937000, 953001, 1000):
            end = start + 999
            try:
                res = await client.fetch_data(SVC, start, end, timeout=15)
            except Exception as e:
                print(f"  page {start}: ERROR {e}")
                continue
                
            if not res or SVC not in res:
                print(f"  page {start}: empty")
                continue
            
            block = res[SVC]
            code = block.get("RESULT", {}).get("CODE", "")
            if code != "INFO-000":
                print(f"  page {start}: code={code}")
                continue
            
            items = block.get("row", [])
            total += len(items)
            
            for item in items:
                chng = item.get("CHNG_DT", "")
                if chng == TODAY:
                    lcns = item.get("LCNS_NO", "?")
                    name = item.get("BSSH_NM", "?")
                    print(f"  *** TODAY FOUND at page {start}: LCNS={lcns} NAME={name} CHNG_DT={chng}")
                    today_found.append(item)
            
            # 진행 표시
            if (start - 937000) % 5000 == 0:
                print(f"  scanned up to {start+999:,} ... today={len(today_found)}")
        
        print(f"\n=== RESULT ===")
        print(f"Total records scanned: {total}")
        print(f"Today ({TODAY}) records: {len(today_found)}")
        for t in today_found:
            print(f"  LCNS={t.get('LCNS_NO')} | {t.get('BSSH_NM')} | CHNG_DT={t.get('CHNG_DT')}")

asyncio.run(main())
