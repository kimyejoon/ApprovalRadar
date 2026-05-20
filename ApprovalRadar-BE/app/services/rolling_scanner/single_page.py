import asyncio
from datetime import datetime, timedelta
from app.core.logger import logger
from app.core.events import shutdown_event
from app.services.pivot_manager import compute_page_fingerprint

PAGE_SIZE = 1000

async def scan_single_page(
    scanner, svc: str, page_start: int, total_count: int,
    fingerprints: dict, scan_times: dict
) -> tuple:
    """단일 페이지 스캔 + fingerprint 비교."""
    if shutdown_event.is_set():
        return (0, [], 0, [])

    page_end = min(page_start + PAGE_SIZE - 1, total_count)
    fp_key = str(page_start)

    try:
        data = await scanner.api_client.fetch_data(
            scanner.service_id, page_start, page_end
        )
    except Exception as e:
        logger.warning(f"[{svc}] ⚠ 페이지 {page_start:,} API 실패 → skip 후 계속: {e}")
        return (0, [], 0, [])

    if not data or scanner.service_id not in data:
        return (1, [], 0, [])

    rows = data[scanner.service_id].get("row", [])
    if not rows:
        return (1, [], 0, [])

    new_fp = compute_page_fingerprint(rows)
    old_fp = fingerprints.get(fp_key)
    fingerprints[fp_key] = new_fp
    scan_times[fp_key] = datetime.now().isoformat()

    mismatch = 0
    new_rows = []

    if old_fp and old_fp != new_fp:
        mismatch = 1
        from database import get_db
        today_str = datetime.now().strftime("%Y%m%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        lcns_list = [r.get("LCNS_NO", "") for r in rows if r.get("LCNS_NO")]
        existing_set = set()
        if lcns_list:
            with get_db() as conn:
                ph = ",".join(["?"] * len(lcns_list))
                db_rows = conn.execute(
                    f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({ph})",
                    lcns_list
                ).fetchall()
                for r in db_rows:
                    existing_set.add((r["license_no"], r["last_event_date"]))

        for row in rows:
            lcns = row.get("LCNS_NO", "")
            chng_dt = row.get("CHNG_DT", "")
            if lcns and chng_dt in (today_str, yesterday_str):
                if (lcns, chng_dt) not in existing_set:
                    new_rows.append(row)

    return (1, new_rows, mismatch, rows)
