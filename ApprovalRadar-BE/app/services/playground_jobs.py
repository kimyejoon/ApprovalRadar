import asyncio
from app.core.logger import logger


async def run_range_scan_job(start: int, end: int, pages: int):
    """지정 범위를 즉시 스캔합니다. start~end 구간의 페이지를 순차 스캔."""
    from app.clients.foodsafety_api import ApiClient
    from app.repositories.state_repository import StateRepository
    from app.services.rolling_scanner import RollingScanner

    svc = "I2861"
    api_client = ApiClient()
    state_repo = StateRepository()
    scanner = RollingScanner(api_client, svc, state_repo)

    state = state_repo.load_state(svc)
    fingerprints = state.get("page_fingerprints", {})
    scan_times = state.get("page_scan_times", {})

    max_pages = pages

    # flush callback — scraper 파이프라인으로
    async def _flush(rows):
        from scraper import run_scraper_for_service_with_rows
        await run_scraper_for_service_with_rows(svc, rows, collected_by="range_scan")

    scanned, new_rows, mismatch, _ = await scanner._scan_range(
        svc, start, start, end,
        max_pages, fingerprints, scan_times, "RANGE"
    )

    if new_rows:
        await _flush(new_rows)
        logger.info(
            f"[Playground] ✅ Range Scan 완료: {scanned}p, {len(new_rows)}건 수집"
        )
    else:
        logger.info(f"[Playground] ✅ Range Scan 완료: {scanned}p, 신규 0건")

    # 상태 저장 (fingerprints + scan_times 업데이트)
    state["page_fingerprints"] = fingerprints
    state["page_scan_times"] = scan_times
    state_repo.save_state(svc, state)


def run_oldest_first_job():
    """Oldest-First Rolling Scan 즉발: 연식 1h 이상 페이지 우선 전수 스캔."""
    import asyncio as _asyncio
    from app.core.config import settings as _s
    from app.clients.foodsafety_api import ApiClient
    from app.repositories.state_repository import StateRepository
    from app.services.rolling_scanner import RollingScanner

    async def _inner():
        svc_ids = getattr(_s, "SERVICES", ["I2861"])
        async with ApiClient() as api_client:
            for svc_id in svc_ids:
                state_repo = StateRepository()
                scanner = RollingScanner(api_client, svc_id, state_repo)

                async def flush_cb(rows):
                    from scraper import run_scraper_for_service_with_rows
                    await run_scraper_for_service_with_rows(
                        svc_id, rows, collected_by="oldest_first_manual"
                    )

                await scanner._scan_oldest_first(flush_callback=flush_cb)

    _asyncio.run(_inner())


async def run_chng_dt_poller_job():
    """I2500 CHNG_DT Poller 즉시 실행"""
    from app.services.chng_dt_poller import poll_today_changes
    result = await poll_today_changes()
    logger.info(
        f"[Playground] CHNG_DT Poller 완료: "
        f"전체 {result['total']}건, 신규 {result['new']}건, 스킵 {result['skipped']}건"
    )
