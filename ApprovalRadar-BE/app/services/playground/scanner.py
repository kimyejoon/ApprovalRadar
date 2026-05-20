import asyncio
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
        from app.repositories.state_repository import StateRepository
        from app.services.rolling_scanner import RollingScanner

        svc = "I2861"
        api_client = ApiClient()
        state_repo = StateRepository()
        scanner = RollingScanner(api_client, svc, state_repo)

        state = state_repo.load_state(svc)
        fingerprints = state.get("page_fingerprints", {})
        scan_times = state.get("page_scan_times", {})

        async def _flush(rows):
            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows(svc, rows, collected_by="range_scan")

        scanned, new_rows, mismatch, _ = await scanner._scan_range(
            svc, start, start, end,
            pages, fingerprints, scan_times, "RANGE"
        )

        if new_rows:
            await _flush(new_rows)
            logger.info(
                f"[Playground] ✅ Range Scan 완료: {scanned}p, {len(new_rows)}건 수집"
            )
        else:
            logger.info(f"[Playground] ✅ Range Scan 완료: {scanned}p, 신규 0건")

        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        state_repo.save_state(svc, state)

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
    page_timestamps = extra.get("page_timestamps", {})

    total_pages = (total_count + 999) // 1000 if total_count > 0 else 0

    entries = []
    for p in range(total_pages):
        page_start = p * 1000 + 1
        fp = fingerprints.get(str(page_start))
        
        if service_id == "I2861":
            ts_val = page_timestamps.get(str(p + 1))
            # UI가 Date 포맷 파싱을 수행할 수 있도록 ISO 포맷 문자열로 변환
            if ts_val:
                import datetime
                ts = datetime.datetime.fromtimestamp(ts_val).isoformat()
            else:
                ts = None
        else:
            ts = scan_times.get(str(page_start))

        label = page_labels.get(str(p + 1))

        entries.append({
            "page_number": p + 1,
            "page_start": page_start,
            "fingerprint": fp[:12] if fp else (None if service_id != "I2861" else "LIVE-SCAN"),
            "last_scanned": ts,
            "label": label,
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
