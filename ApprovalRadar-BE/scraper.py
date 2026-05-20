import asyncio
import sys

# 외부 모듈 호환성을 위해 핵심 수집 함수들을 이관한 모듈로부터 노출
from app.services.scraper.service import run_scraper_for_service, run_scraper_for_service_with_rows
from app.services.scraper.mapper import map_row_fields, parse_datetime_fields

async def run_all_scrapers():
    """
    설정 파일(settings.SERVICES)에 정의된 모든 활성 서비스에 대하여
    차분 동기화(Delta Sync / Rolling Scan)를 실행합니다.
    """
    from app.core.config import settings
    from app.clients.foodsafety_api import ApiClient
    from app.services.diff_crawler.engine import DiffCrawlerEngine
    from app.core.logger import logger

    logger.info("[스크래퍼] Oldest-First Scan 시작 — 전체 서비스 순차 실행...")
    services = getattr(settings, "SERVICES", ["I2859", "I2861"])
    async with ApiClient() as api_client:
        for svc_id in services:
            try:
                crawler = DiffCrawlerEngine(api_client=api_client, service_id=svc_id)
                await crawler.scan_for_updates()
            except Exception as e:
                logger.error(f"❌ [{svc_id}] 차분 동기화 실행 중 오류 발생: {e}")
    logger.info("[스크래퍼] 전체 서비스 Oldest-First Scan 완료")

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
