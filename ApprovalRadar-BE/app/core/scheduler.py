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


def _evening_chng_dt_job():
    """
    [전략 C 보조] 매일 19:00 CHNG_DT=오늘 직접 쿼리 — 전략 A(Ping+Shift) 안전망.

    API는 저녁 7시 이후에만 당일 변동분 CHNG_DT 조회를 허용합니다.
    전략 A가 놓쳤을 가능성이 있는 당일 변동분을 직접 확인하여
    DB에 없는 건만 저장 + SSE 발행합니다.

    ※ 메인 전략은 반드시 A (Ping + Shift 진단).
       C는 하루 1회 19:00 교차검증 역할만 담당합니다.
    """
    import datetime
    from app.core.config import settings
    from app.clients.foodsafety_api import ApiClient

    async def _run():
        today_str = datetime.date.today().strftime("%Y%m%d")
        logger.info(
            f"[전략C] 19:00 CHNG_DT={today_str} 당일 변동분 직접 조회 시작"
        )
        service_ids = getattr(settings, "SERVICES", ["I2859", "I2861"])
        found_total = 0

        async with ApiClient() as api_client:
            for svc_id in service_ids:
                try:
                    # 전체 건수 먼저 확인 (1건 조회로 total_count 파악)
                    res = await api_client.fetch_data(
                        svc_id, 1, 1, CHNG_DT=today_str
                    )
                    total = res.get(svc_id, {}).get("total_count", 0)
                    if isinstance(total, str):
                        total = int(total)
                    if total == 0:
                        logger.info(f"[전략C] {svc_id} CHNG_DT={today_str} 변동분 없음")
                        continue

                    logger.info(
                        f"[전략C] {svc_id} 오늘 변동분 총 {total:,}건 발견 "
                        f"→ 전체 수집 시작"
                    )

                    # 전체 페이지 순회하여 수집
                    all_rows = []
                    page_size = 1000
                    start = 1
                    while start <= total:
                        end = min(start + page_size - 1, total)
                        page_res = await api_client.fetch_data(
                            svc_id, start, end, CHNG_DT=today_str
                        )
                        rows = page_res.get(svc_id, {}).get("row", [])
                        all_rows.extend(rows)
                        start += page_size

                    if not all_rows:
                        continue

                    # DB에 없는 신규 건만 필터링
                    # [Feedback-3 Fix] api_raw_data LIKE 풀스캔 → businesses.license_no 직접 조회 (O(1))
                    # 기존: "SELECT 1 FROM api_raw_data WHERE service_id=? AND response_data LIKE ?"
                    # → api_raw_data에 service_id 컬럼 없음 + LIKE 풀스캔 O(n) 성능 문제
                    # 변경: businesses.license_no PK 조회 (인덱스 활용, O(1))
                    from database import get_db
                    new_rows = []
                    with get_db() as conn:
                        for row in all_rows:
                            lcns_no = row.get("LCNS_NO", "")
                            chng_dt = row.get("CHNG_DT", "")
                            if not lcns_no:
                                continue
                            # businesses 테이블에서 license_no + last_event_date 복합 조건으로 중복 체크
                            # LCNS_NO가 같아도 CHNG_DT가 다른 변동분은 신규로 처리
                            exists = conn.execute(
                                "SELECT 1 FROM businesses WHERE license_no = ? AND last_event_date = ? LIMIT 1",
                                (lcns_no, chng_dt)
                            ).fetchone()
                            if not exists:
                                new_rows.append(row)



                    if new_rows:
                        logger.info(
                            f"[전략C] {svc_id} DB 미수집 신규 {len(new_rows)}/{len(all_rows)}건 발견 "
                            f"→ scraper 파이프라인으로 처리 (DB 저장 + SSE 발행)"
                        )
                        from scraper import run_scraper_for_service_with_rows
                        await run_scraper_for_service_with_rows(svc_id, new_rows)
                        found_total += len(new_rows)
                    else:
                        logger.info(
                            f"[전략C] {svc_id} 오늘 {len(all_rows)}건 모두 이미 수집됨 — 전략 A 정상 작동 확인"
                        )
                except Exception as e:
                    logger.error(f"[전략C] {svc_id} 처리 실패: {e}")

        if found_total > 0:
            logger.info(
                f"[전략C] 완료 — 전략 A가 놓친 {found_total}건 추가 수집 완료"
            )
        else:
            logger.info("[전략C] 완료 — 전략 A가 모든 변동분을 정상 수집함 ✅")

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

    # ✅ [전략 C 보조] 매일 19:00 CHNG_DT=오늘 직접 쿼리 교차검증
    # 메인 전략 A(Ping+Shift)의 안전망 역할. API가 7시 이후 당일 변동분 허용.
    # 전략 A가 놓친 건 있으면 DB 저장 + SSE 발행. 없으면 전략 A 정상 확인 로그만 출력.
    scheduler.add_job(_evening_chng_dt_job, 'cron', hour=19, minute=0, id="evening_chng_dt_job")

    # ✅ [저녁 고밀도 폴링] 18:30~20:30 구간 10분 주기 (평일만)
    # 19시 배치 실행 직후 감지 지연: 30분 → 10분으로 단축
    # 추가 API 비용: ~18회/주기 × 8주기 ≈ 144회/일 (5키 한도 내)
    scheduler.add_job(_evening_dense_poll_start, 'cron', hour=18, minute=30,
                      day_of_week='mon-fri', id="evening_dense_start_job")
    scheduler.add_job(_evening_dense_poll_end, 'cron', hour=20, minute=30,
                      day_of_week='mon-fri', id="evening_dense_end_job")

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


# ── 저녁 고밀도 폴링: 18:30~20:30 구간 10분 주기 ────────────────────────────
# 목적: 19시 배치 실행 직후 감지 지연을 30분 → 10분으로 단축
# 평일(월~금)에만 동작. 18:30에 10분으로 압축, 20:30에 원래 주기 복원.
_base_interval_before_evening: int = 30  # 복원용 기준 주기 저장


def _evening_dense_poll_start():
    """18:30 — 폴링 주기를 10분으로 압축 (평일에만 실행)."""
    global _base_interval_before_evening
    if datetime.now().weekday() >= 5:  # 토·일 스킵
        return
    from app.core.config import settings as _s
    _base_interval_before_evening = _s.SCRAPER_INTERVAL_MINUTES
    logger.info(
        f"[저녁 고밀도 폴링] 18:30 — 주기 {_base_interval_before_evening}분 → 10분으로 압축 "
        f"(19시 배치 감지 지연 단축)"
    )
    reschedule_scraper_job(10)
    _s.SCRAPER_INTERVAL_MINUTES = 10


def _evening_dense_poll_end():
    """20:30 — 폴링 주기를 원래 값으로 복원."""
    global _base_interval_before_evening
    if datetime.now().weekday() >= 5:  # 토·일 스킵
        return
    from app.core.config import settings as _s
    restore = _base_interval_before_evening
    logger.info(
        f"[저녁 고밀도 폴링] 20:30 — 주기 10분 → {restore}분으로 복원"
    )
    reschedule_scraper_job(restore)
    _s.SCRAPER_INTERVAL_MINUTES = restore
