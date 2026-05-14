from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.core.logger import logger
from scraper import run_all_scrapers
from database import vacuum_db, backup_db

scheduler = BackgroundScheduler()

def _check_api_key_recovery():
    """30분마다 소진된 API 키 회복 여부를 자동 체크."""
    from app.clients.foodsafety_api import ApiClient
    from app.core.config import settings
    ApiClient.check_key_recovery(
        settings.API_KEYS,
        settings.BASE_URL,
        settings.DATA_TYPE,
    )

def start_scheduler():
    logger.info("Configuring APScheduler jobs...")
    
    # ✅ [개선] 10분 → 30분: 요구사항 준수 + API Key 일일 1,000건 한도 절약
    scheduler.add_job(run_all_scrapers, 'interval', minutes=30, id="scraper_job")
    
    # 30분마다 소진 키 회복 체크 (소진 상태가 아니면 즉시 반환)
    scheduler.add_job(_check_api_key_recovery, 'interval', minutes=30, id="key_recovery_job")
    
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
