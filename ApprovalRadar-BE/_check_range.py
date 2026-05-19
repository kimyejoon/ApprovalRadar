"""1~30000 구간에서 오늘 날짜(CHNG_DT) 존재 여부 조회"""
import asyncio
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datetime import datetime
from app.clients.foodsafety_api import ApiClient

TODAY = datetime.now().strftime("%Y%m%d")
SVC = "I2861"
PAGE_SIZE = 1000

async def main():
    async with ApiClient() as client:
        today_found = 0
        total_rows = 0
        today_samples = []
        chng_dt_dist = {}
        lcns_samples = []
        bssh_nm_samples = []  # 상호명 정렬 패턴

        for start in range(1, 30001, PAGE_SIZE):
            end = start + PAGE_SIZE - 1
            res = await client.fetch_data(SVC, start, end, timeout=15)
            if not res or SVC not in res:
                continue
            block = res[SVC]
            code = block.get("RESULT", {}).get("CODE", "")
            if code != "INFO-000":
                continue
            items = block.get("row", [])
            total_rows += len(items)

            for item in items:
                dt = item.get("CHNG_DT", "")
                yr = dt[:4] if len(dt) >= 4 else "????"
                chng_dt_dist[yr] = chng_dt_dist.get(yr, 0) + 1
                if dt.startswith(TODAY):
                    today_found += 1
                    if len(today_samples) < 10:
                        today_samples.append(
                            f"  idx~{start+items.index(item)} {item.get('BSSH_NM','')} ({item.get('LCNS_NO','')}) DT={dt}"
                        )

            # 상호명 정렬 패턴 (첫 5개)
            if start <= 5000:
                names = [i.get("BSSH_NM","") for i in items[:5]]
                lcns = [i.get("LCNS_NO","") for i in items[:5]]
                bssh_nm_samples.append(f"  [{start:>6,}] names={names}")
                lcns_samples.append(f"  [{start:>6,}] lcns={lcns}")

            if start % 5000 == 1:
                print(f"  scan... {start:,}~{end:,} | total={total_rows:,}, today={today_found}")

            await asyncio.sleep(0.3)

        print(f"\n{'='*60}")
        print(f"[RESULT] Range 1~30,000 Analysis")
        print(f"{'='*60}")
        print(f"  Total records: {total_rows:,}")
        print(f"  Today ({TODAY}) records: {today_found}")
        if today_samples:
            print(f"  Today samples:")
            for s in today_samples:
                print(s)
        else:
            print(f"  >> NO TODAY RECORDS FOUND in 1~30,000!")
        
        print(f"\n  CHNG_DT year distribution:")
        for yr, cnt in sorted(chng_dt_dist.items()):
            bar = "#" * min(50, cnt // 100)
            print(f"    {yr}: {cnt:>6,} {bar}")

        print(f"\n  BSSH_NM (business name) sort pattern (first 5 pages):")
        for s in bssh_nm_samples[:5]:
            print(s)

        print(f"\n  LCNS_NO sort pattern (first 5 pages):")
        for s in lcns_samples[:5]:
            print(s)

if __name__ == "__main__":
    asyncio.run(main())
