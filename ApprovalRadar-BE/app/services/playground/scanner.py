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
    fingerprints = state.get("page_fingerprints", {})
    scan_times = state.get("page_scan_times", {})

    # I2861 전용 extra_state 라벨 및 타임스탬프 로드
    extra = state.get("extra_state", {})
    page_labels = extra.get("page_labels", {})
    page_industries = extra.get("page_industries", {})
    page_timestamps = extra.get("page_timestamps", {})

    total_pages = (total_count + 999) // 1000 if total_count > 0 else 0

    entries = []
    for p in range(total_pages):
        page_start = p * 1000 + 1
        fp = fingerprints.get(str(page_start))

        if service_id == "I2861":
            ts_val = page_timestamps.get(str(p + 1))
            if ts_val:
                # astimezone() 으로 서버 로컬 타임존(KST)을 명시하여 JS가 UTC로 오파싱하는 것을 방지
                import datetime as _dt
                ts = _dt.datetime.fromtimestamp(ts_val, tz=_dt.timezone.utc).astimezone().isoformat()
            else:
                ts = None

        else:
            ts = scan_times.get(str(page_start))

        label = page_labels.get(str(p + 1))
        industry = page_industries.get(str(p + 1))

        entries.append({
            "page_number": p + 1,
            "page_start": page_start,
            "fingerprint": fp[:12] if fp else (None if service_id != "I2861" else "LIVE-SCAN"),
            "last_scanned": ts,
            "label": label,
            "industry": industry,
        })

    if service_id == "I2861":
        scanned = sum(1 for e in entries if e["last_scanned"] is not None)
    else:
        scanned = sum(1 for e in entries if e["fingerprint"] is not None)

    return {
        "total_pages": total_pages,
        "scanned_pages": scanned,
        "entries": entries,
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
