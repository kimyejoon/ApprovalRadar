from typing import Dict, Any
from app.core.logger import logger
from app.clients.foodsafety_api import ApiClient
from app.services.scraper.mapper import map_row_fields, parse_datetime_fields
from app.services.scraper.persister import persist_single_crawl, persist_batch_crawl

async def run_scraper_for_service(service_id: str, start_idx: int, end_idx: int, **kwargs) -> Dict[str, Any]:
    """
    지정한 범위(start_idx ~ end_idx)의 API를 호출하여 크롤링하고 DB에 저장합니다.
    (단건/순차 처리 플로우)
    """
    logger.info(
        f"🚀 [{service_id}] 크롤러 가동: {start_idx:,} ~ {end_idx:,} (크기: {end_idx - start_idx + 1:,}개)"
    )

    async with ApiClient() as client:
        try:
            res = await client.fetch_data(service_id, start_idx, end_idx, **kwargs)
        except Exception as e:
            logger.error(
                f"❌ [{service_id}] API Fetch 실패 ({start_idx}~{end_idx}): {e}"
            )
            return {
                "success": False,
                "inserted": 0,
                "changed": 0,
                "today_changed": 0,
                "error": str(e),
            }

    rows = res.get(service_id, {}).get("row", [])
    if not rows:
        return {
            "success": True,
            "inserted": 0,
            "changed": 0,
            "today_changed": 0,
            "message": "No new data",
        }

    actually_changed, today_changed = persist_single_crawl(service_id, rows)

    return {
        "success": True,
        "inserted": len(rows),
        "changed": actually_changed,
        "today_changed": today_changed,
    }


async def run_scraper_for_service_with_rows(service_id: str, rows: list, collected_by: str = "rolling_scan") -> Dict[str, Any]:
    """
    이미 수집된 API raw_rows를 전달받아, 병렬/배치로 고속 저장하고 가공합니다.
    """
    if not rows:
        return {"success": True, "inserted": 0, "changed": 0, "today_changed": 0, "message": "Empty rows"}

    mapped_rows = []
    skipped_mapping = 0

    for row in rows:
        fields = map_row_fields(service_id, row)
        if not fields or not fields["lcns_no"]:
            skipped_mapping += 1
            continue

        event_date, event_time, license_date, license_time = parse_datetime_fields(
            fields["event_date_raw"], fields["license_date"]
        )

        mapped_rows.append({
            "fields": fields,
            "event_date": event_date,
            "event_time": event_time,
            "license_date": license_date,
            "license_time": license_time,
            "raw_row": row
        })

    if skipped_mapping > 0:
        logger.warning(
            f"  ⚠️ [{service_id}] 필드 매핑 스킵됨: {skipped_mapping}건 (LCNS_NO 누락 등)"
        )

    if not mapped_rows:
        return {
            "success": True,
            "inserted": 0,
            "changed": 0,
            "today_changed": 0,
            "message": "No valid mapped rows",
        }

    stats = persist_batch_crawl(service_id, mapped_rows, collected_by)

    return {
        "success": True,
        "total_fetched": len(rows),
        "new_indexed": stats["new_indexed"],
        "skipped_dup": stats["skipped_dup"],
        "today": stats["today"],
        "yesterday": stats["yesterday"],
    }
