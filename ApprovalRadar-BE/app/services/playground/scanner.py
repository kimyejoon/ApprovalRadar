import asyncio
import datetime
from database import get_db
from app.core.logger import logger
from app.repositories.state_repository import StateRepository


def trigger_range_scan_task(start: int, end: int):
    pages = (end - start + 1000) // 1000
    logger.info(
        f"[Playground] 🎯 Range Scan 트리거: {start:,}~{end:,} ({pages}p)"
    )

    async def _run_range_scan():
        from app.clients.foodsafety_api import ApiClient
        from app.services.diff_crawler.engine import DiffCrawlerEngine

        svc = "I2861"
        async with ApiClient() as api_client:
            engine = DiffCrawlerEngine(api_client=api_client, service_id=svc)
            rows = await engine._fetch_page(start, end)

        if rows:
            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows(svc, rows, collected_by="range_scan")
            logger.info(f"[Playground] ✅ Range Scan 완료: {len(rows):,}건 수집")
        else:
            logger.info("[Playground] ✅ Range Scan 완료: 신규 0건")

        # Range Scan 완료 후 플레이그라운드 상태 갱신 이벤트 발행
        import json
        from app.core.events import broadcaster
        broadcaster.broadcast_sync(
            json.dumps({"type": "PLAYGROUND_UPDATE"}, ensure_ascii=False)
        )

    asyncio.create_task(_run_range_scan())


def get_page_scan_history_data(service_id: str) -> dict:
    state_repo = StateRepository()
    state = state_repo.load_state(service_id)
    total_count = state.get("last_total_count", 0)
    total_pages = (total_count + 999) // 1000 if total_count > 0 else 0

    # page_scan_history 테이블에서 직접 로드 (JSON extra_state 대신)
    from app.repositories.page_scan_repository import PageScanRepository
    scan_data = PageScanRepository().load_all(service_id)
    page_timestamps = scan_data["page_timestamps"]  # {str(page): int(unix_ts)}
    page_labels     = scan_data["page_labels"]
    page_industries = scan_data["page_industries"]

    entries = []
    for p in range(total_pages):
        page_num = p + 1
        page_start = p * 1000 + 1

        ts_val = page_timestamps.get(str(page_num))
        if ts_val:
            import datetime as _dt
            ts = _dt.datetime.fromtimestamp(ts_val, tz=_dt.timezone.utc).astimezone().isoformat()
        else:
            ts = None

        label    = page_labels.get(str(page_num))
        industry = page_industries.get(str(page_num))

        # fingerprint는 I2861에서 의미 없으므로 고정 표시
        fp = "LIVE-SCAN" if ts else None

        entries.append({
            "page_number": page_num,
            "page_start":  page_start,
            "fingerprint": fp,
            "last_scanned": ts,
            "label":   label,
            "industry": industry,
        })

    scanned = sum(1 for e in entries if e["last_scanned"] is not None)
    return {
        "total_pages":    total_pages,
        "scanned_pages":  scanned,
        "entries":        entries,
    }


def get_tail_history_data(service_id: str) -> dict:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT record_date, total_count 
               FROM tail_history 
               WHERE service_id = ? 
               ORDER BY record_date DESC 
               LIMIT 90""",
            (service_id,)
        ).fetchall()

    entries = [
        {"record_date": r["record_date"], "total_count": r["total_count"]}
        for r in reversed(rows)
    ]
    return {"service_id": service_id, "entries": entries}
