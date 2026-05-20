import asyncio
import sys

# 외부 모듈 호환성을 위해 핵심 수집 함수들을 이관한 모듈로부터 노출
from app.services.scraper.service import run_scraper_for_service, run_scraper_for_service_with_rows
from app.services.scraper.mapper import map_row_fields, parse_datetime_fields

if __name__ == "__main__":
    # CLI 직접 실행 시 수동 크롤링 지원
    # 예: python scraper.py I2859 1 1000
    if len(sys.argv) < 4:
        print("Usage: python scraper.py [service_id] [start_idx] [end_idx] {additional_query_params}")
        sys.exit(1)

    svc_id = sys.argv[1]
    start = int(sys.argv[2])
    end = int(sys.argv[3])

    kwargs = {}
    if len(sys.argv) > 4:
        for arg in sys.argv[4:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                kwargs[k] = v

    print(f"[*] Starting manual crawl: {svc_id} ({start} ~ {end}) with kwargs={kwargs}")
    result = asyncio.run(run_scraper_for_service(svc_id, start, end, **kwargs))
    print(f"[*] Done: {result}")
