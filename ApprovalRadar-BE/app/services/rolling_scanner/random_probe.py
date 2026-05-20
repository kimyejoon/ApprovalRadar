import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
from app.core.logger import logger
from database import DB_FILE

PAGE_SIZE = 1000

async def scan_random_probe(
    scanner, svc: str, max_pages: int, total_count: int,
    cursor_a: int, cursor_b: int,
    range_a: tuple, range_b: tuple,
    scan_times: dict | None = None
) -> tuple:
    """전체 범위에서 랜덤 페이지를 샘플링하여 DB 미존재 레코드를 수집합니다."""
    today_str = datetime.now().strftime("%Y%m%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE

    exclude_margin = 30 * PAGE_SIZE
    exclude_a = set(range(
        max(1, cursor_a - exclude_margin),
        min(total_count, cursor_a + exclude_margin) + 1,
        PAGE_SIZE
    ))
    exclude_b = set(range(
        max(1, cursor_b - exclude_margin),
        min(total_count, cursor_b + exclude_margin) + 1,
        PAGE_SIZE
    ))
    excluded = exclude_a | exclude_b

    all_page_starts = [
        p * PAGE_SIZE + 1 for p in range(total_pages)
        if (p * PAGE_SIZE + 1) not in excluded
    ]

    if not all_page_starts:
        return 0, []

    sample_size = min(max_pages, len(all_page_starts))
    sampled_starts = sorted(random.sample(all_page_starts, sample_size))

    logger.info(
        f"[{svc}] 🎲 Random Probe 시작: {sample_size}p (전체 {len(all_page_starts)}p 중 랜덤 샘플링, 오늘={today_str})"
    )

    scanned = 0
    new_rows = []
    today_found = 0
    yesterday_found = 0
    db_miss_count = 0

    db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    db_conn.row_factory = sqlite3.Row

    try:
        for page_start in sampled_starts:
            page_end = min(page_start + PAGE_SIZE - 1, total_count)

            try:
                res = await scanner.api_client.fetch_data(
                    svc, page_start, page_end, timeout=15
                )
            except Exception:
                continue

            if not res or svc not in res:
                continue

            block = res[svc]
            code = block.get("RESULT", {}).get("CODE", "")
            if code != "INFO-000":
                continue

            items = block.get("row", [])
            if not items:
                continue

            scanned += 1

            if scan_times is not None:
                scan_times[str(page_start)] = datetime.now().isoformat()

            lcns_list = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]

            if lcns_list:
                unique_lcns = list(set(lcns_list))
                placeholders = ",".join(["?"] * len(unique_lcns))
                existing = set()
                cursor = db_conn.execute(
                    f"SELECT license_no FROM businesses WHERE license_no IN ({placeholders})",
                    unique_lcns
                )
                for row in cursor.fetchall():
                    existing.add(row["license_no"])

                page_new = [item for item in items if item.get("LCNS_NO", "") and item.get("LCNS_NO") not in existing]
                if page_new:
                    db_miss_count += len(page_new)
                    new_rows.extend(page_new)

            page_today = sum(1 for item in items if item.get("CHNG_DT", "").startswith(today_str))
            page_yesterday = sum(1 for item in items if item.get("CHNG_DT", "").startswith(yesterday_str))
            if page_today > 0:
                today_found += page_today
                logger.info(f"[{svc}] 🎯 오늘 데이터 발견! page {page_start:,}: {page_today}건 (CHNG_DT={today_str})")
            if page_yesterday > 0:
                yesterday_found += page_yesterday

            if scanned % 10 == 0:
                logger.info(
                    f"[{svc}] 📊 Random Probe 진행: {scanned}/{sample_size}p (DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found})"
                )

            await asyncio.sleep(0.3)

    finally:
        try:
            db_conn.close()
        except Exception:
            pass

    logger.info(
        f"[{svc}] ✅ Random Probe 완료: {scanned}p → {len(new_rows)}건 수집 (DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found})"
    )

    return scanned, new_rows

def extract_new_rows(current_items: list, fingerprints: dict, page_start: int) -> list:
    """fingerprint 불일치 페이지에서 신규 삽입 레코드를 추출합니다."""
    return current_items

def build_fingerprints_from_bootstrap(api_client, service_id: str, total_count: int) -> dict:
    """Bootstrap 호환용."""
    return {}
