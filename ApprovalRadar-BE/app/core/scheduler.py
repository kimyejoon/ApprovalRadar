from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.core.logger import logger
from scraper import run_all_scrapers
from database import vacuum_db, backup_db

scheduler = BackgroundScheduler()

def start_scheduler():
    logger.info("Configuring APScheduler jobs...")
    
    # 10분마다 실행되는 정기 크롤링
    scheduler.add_job(run_all_scrapers, 'interval', minutes=10, id="scraper_job")
    
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
    scheduler.shutdown()
