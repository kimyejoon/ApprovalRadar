# pyrefly: ignore [missing-import]
import asyncio
import threading
# pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.core.logger import logger

scheduler = BackgroundScheduler()

# ─── 재진입 방지 Lock ─────────────────────────────────────────────────────────
# Scraper(DiffCrawler)는 장시간 실행될 수 있으므로
# 이전 실행이 끝나기 전에 새 주기가 시작되면 WAF burst + 키 소진이 발생.
# threading.Lock(blocking=False)로 이미 실행 중이면 즉시 스킵.
_scraper_lock = threading.Lock()
_poller_lock  = threading.Lock()  # chng_dt_poller 전용 (scraper와 독립)


def _scraper_job():
    """스케줄러 동기 래퍼: 별도 스레드에서 새 이벤트 루프를 생성하여 비동기 스크래퍼 실행.
    
    [재진입 방지] 이전 주기가 아직 실행 중이면(Oldest-First 스캔 등이 주기를 초과할 경우)
    이번 주기를 스킵하여 WAF burst와 API 키 소진 가속을 방지.
    """
    if not _scraper_lock.acquire(blocking=False):
        logger.warning(
            "[스케줄러] ⏭️ 이전 Scraper 실행 중 → 이번 주기 스킵 "
            "(Oldest-First Scan이 주기를 초과했습니다)"
        )
        return
    try:
        from scraper import run_all_scrapers
        asyncio.run(run_all_scrapers())
    finally:
        _scraper_lock.release()


def _backfill_job():
    """스케줄러 동기 래퍼: 6시간 주기 세부업종 백필 비동기 실행."""
    from app.services.industry_filler import fill_missing_industry_types
    asyncio.run(fill_missing_industry_types())


def _chng_dt_poller_job():
    """스케줄러 동기 래퍼: I2500 CHNG_DT 봇러 실시간 폴링.

    scraper_lock과 독립적으로 동작. I2861 Oldest-First Scan이 수십 분짜리 돌아가는
    동안에도 poller는 독립적으로 CHNG_DT 봇링을 지속합니다.
    """
    if not _poller_lock.acquire(blocking=False):
        logger.warning(
            "[전략C] ⏭️ 이전 CHNG_DT Poller 실행 중 → 이번 주기 스킵"
        )
        return
    try:
        from app.services.chng_dt_poller import _run_poller_async
        asyncio.run(_run_poller_async())
    except Exception as e:
        logger.error(f"[전략C] chng_dt_poller 오류: {e}", exc_info=True)
    finally:
        _poller_lock.release()


def _check_api_key_recovery():
    """10분마다 소진된 API 키 회복 여부를 자동 체크.
    회복 시 Scraper가 유휴 상태이면 즉시 재가동, 실행 중이면 스킵.
    """
    from app.clients.foodsafety_api import ApiClient
    from app.core.config import settings

    async def _run():
        recovered = await ApiClient.check_key_recovery(
            settings.API_KEYS,
            settings.BASE_URL,
            settings.DATA_TYPE,
        )
        if recovered:
            # Scraper 실행 중이면 재가동 불필요 (이미 돌아가고 있음)
            if _scraper_lock.locked():
                logger.info("[키 회복] Scraper 실행 중 → 재가동 스킵 (이미 실행중)")
                return
            logger.info("[키 회복] 스크래퍼 즉시 재가동 트리거...")
            try:
                from scraper import run_all_scrapers
                await run_all_scrapers()
            except Exception as e:
                logger.error(f"[키 회복] 즉시 재가동 실패: {e}")

    asyncio.run(_run())


def start_scheduler():
    logger.info("Configuring APScheduler jobs...")

    from app.core.config import settings as _s
    interval = _s.SCRAPER_INTERVAL_MINUTES
    logger.info(f"크롤링 주기: {interval}분")
    scheduler.add_job(_scraper_job, 'interval', minutes=interval, id="scraper_job")

    # ✅ [전략C] I2500 CHNG_DT 폴러 — I2861과 동일 주기로 병렬 실행
    # scraper_lock과 독립적인 poller_lock 사용 → 두 잡이 서로 블록하지 않음
    scheduler.add_job(_chng_dt_poller_job, 'interval', minutes=interval, id="chng_dt_poller_job")
    logger.info(f"[전략C] CHNG_DT Poller 등록: {interval}분 주기")

    # 10분마다 소진 키 회복 체크 → 회복 시 즉시 크롤링 재가동
    scheduler.add_job(_check_api_key_recovery, 'interval', minutes=10, id="key_recovery_job")

    # ✅ 세부업종(industry_type) 백필 6시간 주기 - Key 소진/네트워크 오류로 중단 시 자동 재시도
    scheduler.add_job(_backfill_job, 'interval', hours=6, id="backfill_job")

    # DB 최적화 (일요일 새벽 3시)
    from database import vacuum_db, backup_db, prune_db
    scheduler.add_job(vacuum_db, 'cron', day_of_week='sun', hour=3, minute=0, id="vacuum_job")

    # DB 백업 (매일 새벽 4시)
    scheduler.add_job(backup_db, 'cron', hour=4, minute=0, id="backup_job")

    # DB 오래된 데이터 자동 정리 (매일 새벽 3시 30분)
    scheduler.add_job(lambda: prune_db(days=7), 'cron', hour=3, minute=30, id="db_prune_job")

    # 앱 시작 시 즉시 1회 실행 (blocking 방지를 위해 스케줄러에 위임)
    logger.info("Adding initial catch-up scraper job to background...")
    scheduler.add_job(_scraper_job, 'date', run_date=datetime.now(), id="initial_scraper_job")
    # [전략C] 폴러도 앱 시작 시 즉시 1회 실행
    scheduler.add_job(_chng_dt_poller_job, 'date', run_date=datetime.now(), id="initial_poller_job")

    scheduler.start()
    logger.info("APScheduler started successfully.")



def shutdown_scheduler():
    logger.info("Shutting down APScheduler...")
    scheduler.shutdown(wait=False)


def trigger_immediate_scrape():
    """즉시 Scraper를 실행하도록 예약. (소진 키 복구 등에 활용)
    """
    import time
    ts = int(time.time())

    if _scraper_lock.locked():
        logger.info("[즉발] Scraper 실행 중 → 이번 즉발 스킵 (lock 보유 중)")
        return

    try:
        scheduler.add_job(
            _scraper_job,
            'date',
            run_date=datetime.now(),
            id=f"immediate_scrape_{ts}",
        )
        logger.info("[즉발] Scraper 즉시 실행 등록")
    except Exception as e:
        logger.error(f"[즉발] Scraper 등록 실패: {e}")


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
