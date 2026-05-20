import asyncio
import datetime
import json
import time
from typing import List, Optional, Dict, Any

from database import init_db, get_db
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.services.diff_crawler import DiffCrawlerEngine
from app.services.change_detector import ChangeDetector, ChangeResult, infer_change_type_from_bf_af
from app.core.logger import logger

from app.repositories.business_repository import BusinessRepository
from app.repositories.raw_data_repository import RawDataRepository

from app.services.scraper.mapper import _map_row_fields, _parse_datetime_fields

async def run_scraper_for_service_with_rows(service_id: str, new_data_rows: list, collected_by: str = "rolling_scan"):
    """
    외부에서 수집된 rows를 DB에 저장 + SSE 발행.
    [최적화] batch SELECT로 기존 레코드 조회 후 bulk INSERT/UPDATE.
    """
    start_time = time.time()
    init_db()
    business_repo = BusinessRepository()
    raw_repo = RawDataRepository()
    detector = ChangeDetector()
    now = datetime.datetime.now().isoformat()

    svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(service_id, service_id)
    logger.info(f"🆕 [{svc_name}] flush: {len(new_data_rows)}건 DB 처리 시작 (batch)...")

    # ── Step 1: 필드 매핑 (CPU only, fast) ──
    mapped_rows = []
    for row in new_data_rows:
        fields = _map_row_fields(service_id, row)
        if not fields or not fields["lcns_no"]:
            continue
        event_date, event_time, license_date, license_time = _parse_datetime_fields(
            fields["event_date_raw"], fields["license_date"]
        )
        mapped_rows.append({
            "fields": fields,
            "raw_row": row,
            "event_date": event_date,
            "event_time": event_time,
            "license_date": license_date,
            "license_time": license_time,
        })

    if not mapped_rows:
        logger.info(f"ℹ️ [{svc_name}] flush: 유효 레코드 0건 → 스킵")
        return

    # ── Step 2: batch SELECT — 기존 DB 레코드 한 번에 조회 ──
    all_lcns = [m["fields"]["lcns_no"] for m in mapped_rows]
    # 중복 LCNS_NO 제거 (같은 업소의 여러 변경이력)
    unique_lcns = list(set(all_lcns))

    actually_changed = 0
    skipped_dup = 0

    with get_db() as conn:
        # batch SELECT: 1000건씩 IN절 조회 (SQLite 변수 제한 대응)
        # ── Step 2: batch SELECT — (license_no, last_event_date) 쌍으로 중복 확인 ──
        existing_pairs = set()
        for i in range(0, len(unique_lcns), 500):
            batch = unique_lcns[i:i+500]
            placeholders = ",".join(["?"] * len(batch))
            cursor = conn.execute(
                f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({placeholders})",
                batch
            )
            for row in cursor.fetchall():
                existing_pairs.add((row["license_no"], row["last_event_date"]))

        logger.info(
            f"  📋 batch SELECT 완료: {len(unique_lcns)}건 LCNS 조회, "
            f"기존 이력 {len(existing_pairs)}쌍"
        )

        # ── Step 3: INSERT only (동일 LCNS + 동일 event_date만 스킵) ──
        insert_count = 0
        inserted_lcns_list = []  # Backfill 대상 추적
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        today_changed = 0  # 오늘 변동분만 (SSE 발행 기준)

        for m in mapped_rows:
            fields = m["fields"]
            lcns_no = fields["lcns_no"]
            event_date = m["event_date"]
            event_time = m["event_time"]
            license_date = m["license_date"]
            license_time = m["license_time"]

            pair = (lcns_no, event_date)
            if pair in existing_pairs:
                skipped_dup += 1
                continue

            # 신규 이력 INSERT — BF/AF 기반 스마트 추론
            if fields.get("change_reason"):
                infer_update_type, infer_update_detail = infer_change_type_from_bf_af(
                    fields["change_reason"], fields["change_before"], fields["change_after"]
                )
            else:
                infer_update_type = (
                    "신규등록" if license_date == event_date else "인허가변동"
                )
                infer_update_detail = None
            record = {
                "license_no": lcns_no,
                "business_name": fields["business_name"],
                "address": fields["address"],
                "representative_name": fields["representative_name"],
                "business_status": fields["business_status"],
                "license_date": license_date,
                "phone_number": fields["phone_number"],
                "industry_type": fields["industry_type"],
                "last_event_date": event_date,
                "infer_update_type": infer_update_type,
                "infer_update_detail": infer_update_detail,
                "last_event_time": event_time,
                "license_time": license_time,
                "change_reason": fields.get("change_reason"),
                "change_before": fields.get("change_before"),
                "change_after": fields.get("change_after"),
                "collected_by": collected_by,
            }
            business_repo.insert_business(record, conn=conn)
            raw_repo.insert_raw_data(lcns_no, json.dumps(m["raw_row"], ensure_ascii=False), now, conn=conn)
            insert_count += 1
            actually_changed += 1
            inserted_lcns_list.append(lcns_no)
            if event_date == today_str:
                today_changed += 1
            # 중복 INSERT 방지
            existing_pairs.add(pair)

        conn.commit()

    elapsed = time.time() - start_time

    # ── 결과 요약 + SSE 발행 ──
    log_suffix = f"(오늘:{today_changed})" if today_changed > 0 else ""
    if actually_changed > 0:
        logger.info(
            f"✅ [{svc_name}] flush 완료: {len(mapped_rows)}건 → "
            f"INSERT {insert_count} / 스킵 {skipped_dup} "
            f"({elapsed:.1f}초) {log_suffix}"
        )
    else:
        logger.info(
            f"ℹ️ [{svc_name}] flush 완료: {len(mapped_rows)}건 모두 이미 수집됨 "
            f"({skipped_dup}건 스킵, {elapsed:.1f}초)"
        )

    if today_changed > 0:
        from app.core.events import broadcaster
        update_data = json.dumps(
            {"type": "UPDATE", "count": today_changed}, ensure_ascii=False
        )
        broadcaster.broadcast_sync(update_data)
        logger.info(
            f"🔔 [{svc_name}] 오늘 변동분 {today_changed}건 감지 → SSE 발행!"
        )

    # ── 신규 INSERT 건 → 즉시 세부업종 Backfill ──
    if inserted_lcns_list:
        unique_lcns = list(dict.fromkeys(inserted_lcns_list))
        import threading
        from app.services.industry_filler import fill_industry_for_licenses
        logger.info(
            f"[즉시 Backfill] {len(unique_lcns)}건 I2500 백필 → 백그라운드 시작"
        )
        threading.Thread(
            target=lambda lcns=unique_lcns: asyncio.run(fill_industry_for_licenses(lcns)),
            daemon=True,
            name=f"BackfillThread-flush-{service_id}",
        ).start()
