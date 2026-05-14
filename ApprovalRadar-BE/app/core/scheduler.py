# pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.core.logger import logger
from scraper import run_all_scrapers
from database import vacuum_db, backup_db

scheduler = BackgroundScheduler()

def _check_api_key_recovery():
    """10분마다 소진된 API 키 회복 여부를 자동 체크. 회복 시 즉시 크롤럁 잡."""
    from app.clients.foodsafety_api import ApiClient
    from app.core.config import settings
    recovered = ApiClient.check_key_recovery(
        settings.API_KEYS,
        settings.BASE_URL,
        settings.DATA_TYPE,
    )
    if recovered:
        # 회복 확인 시: 다음 scraper_job 주기(30분)까지 기다리지 않고 즉시 크롤링 실행
        logger.info("[키 회복] 스크래퍼 즉시 재가동 트리거...")
        try:
            from scraper import run_all_scrapers
            run_all_scrapers()
        except Exception as e:
            logger.error(f"[키 회복] 즉시 재가동 실패: {e}")

def start_scheduler():
    logger.info("Configuring APScheduler jobs...")
    
    # ✅ [개선] 10분 → 30분: 요구사항 준수 + API Key 일일 1,000건 한도 절약
    # 주기는 settings.SCRAPER_INTERVAL_MINUTES (기본 30분, .env의 SCRAPER_INTERVAL_MINUTES로 오버라이드 가능)
    from app.core.config import settings as _s
    interval = _s.SCRAPER_INTERVAL_MINUTES
    logger.info(f"크롤링 주기: {interval}분")
    scheduler.add_job(run_all_scrapers, 'interval', minutes=interval, id="scraper_job")
    
    # 10분마다 소진 키 회복 체크 → 회복 시 즉시 크롤링 재가동
    scheduler.add_job(_check_api_key_recovery, 'interval', minutes=10, id="key_recovery_job")
    
    # ✅ [개선] 세부업종(industry_type) 백필 6시간 주기 - Key 소진/네트워크 오류로 중단 시 자동 재시도
    from app.services.industry_filler import fill_missing_industry_types
    scheduler.add_job(fill_missing_industry_types, 'interval', hours=6, id="backfill_job")
    
    # DB 최적화 (일요일 새벽 3시)
    scheduler.add_job(vacuum_db, 'cron', day_of_week='sun', hour=3, minute=0, id="vacuum_job")
    
    # DB 백업 (매일 새벽 4시)
    scheduler.add_job(backup_db, 'cron', hour=4, minute=0, id="backup_job")
    
    # 앱 시작 시 대기(Block)를 막기 위해, 즉시 1회 실행하는 작업을 백그라운드 스케줄러로 던집니다.
    logger.info("Adding initial catch-up scraper job to background...")
    scheduler.add_job(run_all_scrapers, 'date', run_date=datetime.now(), id="initial_scraper_job")
    
    scheduler.start()
    logger.info("APScheduler started successfully.")

def shutdown_scheduler():
    logger.info("Shutting down APScheduler...")
    scheduler.shutdown(wait=False)
