import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.logger import logger
from app.services.pivot_manager import compute_page_fingerprint
from database import DB_FILE

PAGE_SIZE = 1000

async def scan_range(
    scanner, svc: str, cursor: int,
    range_start: int, range_end: int,
    max_pages: int, fingerprints: dict, scan_times: dict,
    label: str
) -> tuple:
    """지정된 범위 내에서 cursor부터 max_pages만큼 스캔합니다."""
    scanned = 0
    new_rows = []
    mismatched = 0
    new_fp_count = 0
    match_count = 0
    today_found = 0
    yesterday_found = 0
    db_miss_count = 0
    today_str = datetime.now().strftime("%Y%m%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    all_chng_dts = []
    lcns_sort_asc = 0
    lcns_sort_desc = 0
    lcns_no_sort = 0

    db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    db_conn.row_factory = sqlite3.Row

    logger.info(
        f"[{svc}] 📡 커서 {label} 스캔 시작: "
        f"범위 {cursor:,}~{range_end:,}, 최대 {max_pages}페이지 (오늘={today_str})"
    )

    try:
        while scanned < max_pages:
            page_start = cursor

            if page_start > range_end:
                cursor = range_start
                logger.info(
                    f"[{svc}] 🔁 커서 {label} 1회전 완료! cursor를 {range_start:,}으로 리셋"
                )
                break

            page_end = min(page_start + PAGE_SIZE - 1, range_end)
            try:
                res = await scanner.api_client.fetch_data(
                    svc, page_start, page_end, timeout=30
                )
                await asyncio.sleep(
                    random.uniform(settings.GAP_MIN, settings.GAP_MAX)
                )

                if not res or svc not in res:
                    cursor += PAGE_SIZE
                    scanned += 1
                    continue

                block = res[svc]
                code = block.get("RESULT", {}).get("CODE", "")

                if code in ("INFO-200", "") or code != "INFO-000":
                    cursor += PAGE_SIZE
                    scanned += 1
                    continue

                items = block.get("row", [])
                if not items:
                    cursor += PAGE_SIZE
                    scanned += 1
                    continue

            except Exception as e:
                logger.warning(
                    f"[{svc}] Rolling Scan {label} page {page_start:,} 조회 실패: {e}"
                )
                cursor += PAGE_SIZE
                scanned += 1
                continue

            lcns_list = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]
            if lcns_list:
                placeholders = ",".join(["?"] * len(lcns_list))
                existing_cursor = db_conn.execute(
                    f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({placeholders})",
                    lcns_list
                )
                existing_pairs = {(row[0], row[1]) for row in existing_cursor.fetchall()}

                missing_items = [
                    item for item in items
                    if item.get("LCNS_NO", "")
                    and (item["LCNS_NO"], item.get("CHNG_DT", "")) not in existing_pairs
                ]
                if missing_items:
                    db_miss_count += len(missing_items)
                    new_rows.extend(missing_items)

                    today_in_missing = sum(
                        1 for item in missing_items
                        if item.get("CHNG_DT", "") == today_str
                    )
                    yesterday_in_missing = sum(
                        1 for item in missing_items
                        if item.get("CHNG_DT", "") == yesterday_str
                    )
                    if today_in_missing:
                        today_found += today_in_missing
                    if yesterday_in_missing:
                        yesterday_found += yesterday_in_missing
                        logger.info(
                            f"[{svc}] 🆕 커서 {label} page {page_start:,}: 오늘({today_str}) 변동분 {today_in_missing}건 즉시 감지!"
                        )

                    if len(missing_items) >= 5:
                        logger.info(
                            f"[{svc}] 📥 커서 {label} page {page_start:,}: DB 미존재 {len(missing_items)}건 발견 → 수집 대상 추가"
                        )

            current_fp = compute_page_fingerprint(items)
            stored_fp = fingerprints.get(str(page_start), "")
            scan_times[str(page_start)] = datetime.now().isoformat()

            if not stored_fp:
                new_fp_count += 1
            elif current_fp == stored_fp:
                match_count += 1
            else:
                mismatched += 1
                logger.debug(
                    f"[{svc}] 커서 {label} page {page_start:,}: fingerprint 불일치 (DB miss 체크에서 이미 처리)"
                )

            page_chng_dts = [item.get("CHNG_DT", "") for item in items if item.get("CHNG_DT")]
            all_chng_dts.extend(page_chng_dts)

            lcns_nos = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]
            if len(lcns_nos) >= 2:
                is_asc = all(lcns_nos[i] <= lcns_nos[i+1] for i in range(min(10, len(lcns_nos)-1)))
                is_desc = all(lcns_nos[i] >= lcns_nos[i+1] for i in range(min(10, len(lcns_nos)-1)))
                if is_asc:
                    lcns_sort_asc += 1
                elif is_desc:
                    lcns_sort_desc += 1
                else:
                    lcns_no_sort += 1

            fingerprints[str(page_start)] = current_fp
            cursor += PAGE_SIZE
            scanned += 1

            if scanned % 10 == 0:
                insight = ""
                if all_chng_dts:
                    sorted_dts = sorted(all_chng_dts)
                    oldest = sorted_dts[0]
                    newest = sorted_dts[-1]
                    year_dist = {}
                    for dt in all_chng_dts:
                        yr = dt[:4] if len(dt) >= 4 else "????"
                        year_dist[yr] = year_dist.get(yr, 0) + 1
                    top_years = sorted(year_dist.items(), key=lambda x: -x[1])[:3]
                    yr_summary = " ".join(f"{y}:{c}" for y, c in top_years)
                    sort_pattern = f"LCNS정렬:↑{lcns_sort_asc}/↓{lcns_sort_desc}/∅{lcns_no_sort}"
                    insight = f" | DT범위:{oldest}~{newest} 연도분포:[{yr_summary}] {sort_pattern}"

                logger.info(
                    f"[{svc}] 📊 커서 {label} 진행: {scanned}/{max_pages}p "
                    f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
                    f"DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found}){insight}"
                )

    finally:
        try:
            db_conn.close()
        except Exception:
            pass

    if today_found > 0:
        logger.info(f"[{svc}] 🆕 커서 {label}: 오늘({today_str}) 변동분 {today_found}건 즉시 감지!")
    if yesterday_found > 0:
        logger.info(f"[{svc}] 📋 커서 {label}: 어제({yesterday_str}) 변동분 {yesterday_found}건 감지")
    logger.info(
        f"[{svc}] ✅ 커서 {label} 완료: {scanned}p 스캔 "
        f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
        f"DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found}) → {len(new_rows)}건 수집"
    )

    return scanned, new_rows, mismatched, cursor
