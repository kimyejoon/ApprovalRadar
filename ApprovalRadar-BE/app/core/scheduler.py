# pyrefly: ignore [missing-import]
import asyncio
# pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.core.logger import logger

scheduler = BackgroundScheduler()


def _scraper_job():
    """스케줄러 동기 래퍼: 별도 스레드에서 새 이벤트 루프를 생성하여 비동기 스크래퍼 실행."""
    from scraper import run_all_scrapers
    asyncio.run(run_all_scrapers())


def _backfill_job():
    """스케줄러 동기 래퍼: 6시간 주기 세부업종 백필 비동기 실행."""
    from app.services.industry_filler import fill_missing_industry_types
    asyncio.run(fill_missing_industry_types())


def _check_api_key_recovery():
    """10분마다 소진된 API 키 회복 여부를 자동 체크. 회복 시 즉시 크롤링 잡 재가동."""
    from app.clients.foodsafety_api import ApiClient
    from app.core.config import settings

    async def _run():
        recovered = await ApiClient.check_key_recovery(
            settings.API_KEYS,
            settings.BASE_URL,
            settings.DATA_TYPE,
        )
        if recovered:
            logger.info("[키 회복] 스크래퍼 즉시 재가동 트리거...")
            try:
                from scraper import run_all_scrapers
                await run_all_scrapers()
            except Exception as e:
                logger.error(f"[키 회복] 즉시 재가동 실패: {e}")

    asyncio.run(_run())


def _daily_bootstrap_job():
    """매일 09:00 실행: 모든 서비스의 피벗을 재생성하여 당일 변동 감지 준비."""
    from app.core.config import settings
    from app.clients.foodsafety_api import ApiClient
    from app.services.diff_crawler import DiffCrawlerEngine

    async def _run():
        logger.info("[일일 Bootstrap] 09:00 피벗 재생성 시작 — 전날 밤 API 재정렬 반영")
        service_ids = getattr(settings, "SERVICES", ["I2859", "I2861"])
        async with ApiClient() as api_client:
            for svc_id in service_ids:
                try:
                    crawler = DiffCrawlerEngine(api_client=api_client, service_id=svc_id)
                    state = await crawler.bootstrap()
                    logger.info(
                        f"[일일 Bootstrap] {svc_id} 피벗 재생성 완료 — "
                        f"{len(state.get('pivots', {}))}개 피벗, "
                        f"Tail={state.get('last_total_count', 0):,}건"
                    )
                except Exception as e:
                    logger.error(f"[일일 Bootstrap] {svc_id} 실패: {e}")
        logger.info("[일일 Bootstrap] 전체 완료 — 오늘 하루 변동 감지 준비됨")

    asyncio.run(_run())



def start_scheduler():
    logger.info("Configuring APScheduler jobs...")

    from app.core.config import settings as _s
    interval = _s.SCRAPER_INTERVAL_MINUTES
    logger.info(f"크롤링 주기: {interval}분")
    scheduler.add_job(_scraper_job, 'interval', minutes=interval, id="scraper_job")

    # 10분마다 소진 키 회복 체크 → 회복 시 즉시 크롤링 재가동
    scheduler.add_job(_check_api_key_recovery, 'interval', minutes=10, id="key_recovery_job")

    # ✅ 세부업종(industry_type) 백필 6시간 주기 - Key 소진/네트워크 오류로 중단 시 자동 재시도
    scheduler.add_job(_backfill_job, 'interval', hours=6, id="backfill_job")

    # DB 최적화 (일요일 새벽 3시)
    from database import vacuum_db, backup_db
    scheduler.add_job(vacuum_db, 'cron', day_of_week='sun', hour=3, minute=0, id="vacuum_job")

    # DB 백업 (매일 새벽 4시)
    scheduler.add_job(backup_db, 'cron', hour=4, minute=0, id="backup_job")

    # ✅ 매일 09:00 fresh bootstrap — 야간 API 재정렬 후 피벗 재생성
    # 이유: API는 가나다순 재정렬이 수시로 발생 → 전날 피벗이 당일 아침이면 stale
    # 매일 업무 시작 전 피벗 재생성으로 당일 변동 감지 정확도 보장
    scheduler.add_job(_daily_bootstrap_job, 'cron', hour=9, minute=0, id="daily_bootstrap_job")

    # 앱 시작 시 즉시 1회 실행 (blocking 방지를 위해 스케줄러에 위임)
    logger.info("Adding initial catch-up scraper job to background...")
    scheduler.add_job(_scraper_job, 'date', run_date=datetime.now(), id="initial_scraper_job")


    scheduler.start()
    logger.info("APScheduler started successfully.")


def shutdown_scheduler():
    logger.info("Shutting down APScheduler...")
    scheduler.shutdown(wait=False)


def trigger_immediate_scrape():
    """키 회복/추가 시 크롤링을 즉시 1회 실행합니다.
    APScheduler 'date' 잡으로 등록하여 별도 스레드에서 비동기로 안전하게 실행합니다.
    이미 실행 중인 잡과 충돌하지 않습니다 (고유 id를 timestamp로 구분)."""
    import time
    job_id = f"immediate_scrape_{int(time.time())}"
    try:
        scheduler.add_job(
            _scraper_job,
            'date',
            run_date=datetime.now(),
            id=job_id,
        )
        logger.info(f"[즉시 재가동] 크롤러 즉시 실행 잡 등록됨: {job_id}")
    except Exception as e:
        logger.error(f"[즉시 재가동] 잡 등록 실패: {e}")


def reschedule_scraper_job(new_interval_minutes: int) -> None:
    """크롤링 주기를 서버 재시작 없이 실시간 변경합니다.
    기존 scraper_job을 제거하고 새 interval로 재등록합니다."""
    try:
        if scheduler.get_job("scraper_job"):
            scheduler.remove_job("scraper_job")
        scheduler.add_job(
            _scraper_job,
            'interval',
            minutes=new_interval_minutes,
            id="scraper_job",
        )
        logger.info(f"[스케줄러] 크롤링 주기 변경 완료: {new_interval_minutes}분")
    except Exception as e:
        logger.error(f"[스케줄러] 크롤링 주기 변경 실패: {e}")
        raise
