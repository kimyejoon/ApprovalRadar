import json
import datetime
from database import get_db
from app.repositories.business_repository import BusinessRepository
from app.repositories.raw_data_repository import RawDataRepository
from app.services.change_detector import ChangeDetector, infer_change_type_from_bf_af
from app.core.logger import logger
from app.services.scraper.persistence_notifier import trigger_sse_broadcast, trigger_backfill_thread

business_repo = BusinessRepository()
raw_repo = RawDataRepository()
detector = ChangeDetector()

def persist_batch_crawl(service_id: str, mapped_rows: list, collected_by: str) -> dict:
    """
    배치 크롤링 결과를 최적화된 batch SELECT 및 bulk INSERT로 DB에 반영합니다.
    (기존 레코드가 이미 존재할 때, 속성이 하나라도 달라진 경우 단일진실원천(Single Source of Truth)인
     API 데이터를 즉각적이고 효율적으로 Update 반영합니다.)

    Returns: {
        "total_fetched": 조회 건수,
        "new_indexed": 신규 색인 건수,
        "skipped_dup": 미색인(중복 스킵) 건수,
        "today": 오늘 변동 건수 (신규 INSERT 및 UPDATE 기준),
        "yesterday": 어제 변동 건수 (신규 INSERT 및 UPDATE 기준),
        "today_in_page": 오늘 날짜 레코드 건수 (신규+중복 전체),
        "yesterday_in_page": 어제 날짜 레코드 건수 (신규+중복 전체),
    }
    """
    now = datetime.datetime.now().isoformat()
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    yesterday_str = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    all_lcns = [m["fields"]["lcns_no"] for m in mapped_rows]
    unique_lcns = list(set(all_lcns))

    new_indexed = 0
    skipped_dup = 0
    today_count = 0
    yesterday_count = 0
    today_in_page = 0       # 신규+중복 포함 오늘 날짜 레코드 수
    yesterday_in_page = 0   # 신규+중복 포함 어제 날짜 레코드 수
    inserted_lcns_list = []

    with get_db() as conn:
        existing_records = {}
        for i in range(0, len(unique_lcns), 500):
            batch = unique_lcns[i:i+500]
            placeholders = ",".join(["?"] * len(batch))
            cursor = conn.execute(
                f"SELECT id, license_no, last_event_date, business_name, address, representative_name, business_status, phone_number, industry_type, representative_history, licensing_history, infer_update_type, infer_update_detail, change_before FROM businesses WHERE license_no IN ({placeholders})",
                batch
            )
            for r in cursor.fetchall():
                existing_records[(r["license_no"], r["last_event_date"], r.get("change_before") or "")] = dict(r)

        logger.info(
            f"  📋 batch SELECT 완료: {len(unique_lcns)}건 LCNS 조회, "
            f"기존 이력 {len(existing_records)}쌍"
        )

        to_update = []
        to_insert = []
        to_insert_raw = []
        update_log_details = []
        update_raw_logs = []

        for m in mapped_rows:
            fields = m["fields"]
            lcns_no = fields["lcns_no"]
            event_date = m["event_date"]
            event_time = m["event_time"]
            license_date = m["license_date"]
            license_time = m["license_time"]

            change_before_val = fields.get("change_before") or ""
            pair = (lcns_no, event_date, change_before_val)

            # 전체 조회 기준 오늘/어제 카운트 (신규+중복 불문)
            if event_date == today_str:
                today_in_page += 1
            elif event_date == yesterday_str:
                yesterday_in_page += 1

            db_record = existing_records.get(pair)

            if db_record is not None:
                # 이미 존재 -> 속성이 하나라도 달라졌는지 대조 후 즉각 Update
                is_mirror_upgrade = db_record.get("infer_update_type", "") == "mirror"
                change = detector.detect(
                    db_record=db_record,
                    new_rep_name=fields["representative_name"],
                    new_business_status=fields["business_status"],
                    new_business_name=fields["business_name"],
                    now=now,
                )

                has_diff = (
                    change.is_updated
                    or (fields["industry_type"] and not db_record.get("industry_type"))
                    or is_mirror_upgrade
                    or fields["address"] != db_record.get("address")
                    or fields["phone_number"] != db_record.get("phone_number")
                )

                if has_diff:
                    diff_details = []
                    if change.is_updated:
                        diff_details.append(f"change_detector({change.update_type})")
                    if fields["industry_type"] and not db_record.get("industry_type"):
                        diff_details.append(f"industry_type({db_record.get('industry_type')} -> {fields['industry_type']})")
                    if is_mirror_upgrade:
                        diff_details.append("mirror_upgrade")
                    if fields["address"] != db_record.get("address"):
                        diff_details.append(f"address({db_record.get('address')} -> {fields['address']})")
                    if fields["phone_number"] != db_record.get("phone_number"):
                        diff_details.append(f"phone_number({db_record.get('phone_number')} -> {fields['phone_number']})")

                    diff_details_str = ", ".join(diff_details)
                    update_log_details.append(diff_details_str)
                    update_raw_logs.append(f"{lcns_no} ({diff_details_str})")

                    updates = {
                        "business_name": fields["business_name"],
                        "address": fields["address"],
                        "representative_name": fields["representative_name"],
                        "business_status": (
                            fields["business_status"]
                            if fields["business_status"] is not None
                            else db_record.get("business_status")
                        ),
                        "phone_number": fields["phone_number"],
                        "industry_type": (
                            fields["industry_type"] or db_record.get("industry_type")
                        ),
                        "representative_history": json.dumps(
                            change.rep_history, ensure_ascii=False
                        ),
                        "licensing_history": json.dumps(
                            change.lic_history, ensure_ascii=False
                        ),
                        "update_type": change.update_type,
                        "prev_business_status": change.prev_business_status,
                        "prev_representative_name": change.prev_representative_name,
                        "prev_business_name": change.prev_business_name,
                        "infer_update_type": (
                            change.infer_update_type
                            if change.infer_update_type is not None
                            else (None if db_record.get("infer_update_type") == "mirror" else db_record.get("infer_update_type"))
                        ),
                        "infer_update_detail": (
                            change.infer_update_detail
                            if change.infer_update_detail is not None
                            else (None if db_record.get("infer_update_type") == "mirror" else db_record.get("infer_update_detail"))
                        ),
                        "last_event_time": event_time,
                        "license_time": license_time,
                        "updated_at": now,
                    }
                    to_update.append((
                        updates["business_name"], updates["address"], updates["representative_name"], 
                        updates["business_status"], updates["phone_number"], updates.get("industry_type"),
                        updates["representative_history"], updates["licensing_history"],
                        updates.get("update_type"), updates.get("prev_business_status"), updates.get("prev_representative_name"), updates.get("prev_business_name"),
                        updates.get("infer_update_type"), updates.get("infer_update_detail"),
                        updates.get("last_event_time"), updates.get("license_time"),
                        updates["updated_at"], lcns_no, event_date, change_before_val
                    ))
                    to_insert_raw.append((lcns_no, json.dumps(m["raw_row"], ensure_ascii=False), now))
                    new_indexed += 1
                    if event_date == today_str:
                        today_count += 1
                    elif event_date == yesterday_str:
                        yesterday_count += 1
                    
                    # 메모리 캐시 레코드 정보 동기화
                    db_record.update(updates)
                else:
                    skipped_dup += 1
                continue

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
            to_insert.append((
                record["license_no"], record["business_name"], record["address"], 
                record["representative_name"], record["business_status"], 
                record["license_date"], record["phone_number"], record.get("industry_type"), record["last_event_date"],
                record.get("update_type"), record.get("prev_business_status"), 
                record.get("prev_representative_name"), record.get("prev_business_name"), record.get("infer_update_type"), record.get("infer_update_detail"),
                record.get("last_event_time"), record.get("license_time"),
                record.get("change_reason"), record.get("change_before"), record.get("change_after"),
                record.get("collected_by")
            ))
            to_insert_raw.append((lcns_no, json.dumps(m["raw_row"], ensure_ascii=False), now))
            new_indexed += 1
            inserted_lcns_list.append(lcns_no)
            if event_date == today_str:
                today_count += 1
            elif event_date == yesterday_str:
                yesterday_count += 1
            existing_records[pair] = record

        # Batch execute updates and inserts!
        if to_update:
            business_repo.update_businesses_batch(to_update, conn=conn)
            # Group updates by diff details for clean logging
            detail_counts = {}
            for d in update_log_details:
                detail_counts[d] = detail_counts.get(d, 0) + 1
            summary_parts = [f"{k} {v}건" for k, v in sorted(detail_counts.items(), key=lambda x: -x[1])]
            logger.info(
                f"🔄 [속성 변경 감지] DB 레코드와 API 데이터 상이로 총 {len(to_update)}건 즉각 업데이트 수행 "
                f"({', '.join(summary_parts)})"
            )
            if update_raw_logs:
                logger.debug(f"🔍 업데이트 상세 대상: {', '.join(update_raw_logs)}")
        if to_insert:
            business_repo.insert_businesses_batch(to_insert, conn=conn)
        if to_insert_raw:
            raw_repo.insert_raw_data_batch(to_insert_raw, conn=conn)

        conn.commit()

    if today_count > 0:
        trigger_sse_broadcast(today_count, service_id)

    if inserted_lcns_list:
        unique_inserted = list(dict.fromkeys(inserted_lcns_list))
        trigger_backfill_thread(unique_inserted, service_id, f"flush-{service_id}")

    return {
        "total_fetched": len(mapped_rows),
        "new_indexed": new_indexed,
        "skipped_dup": skipped_dup,
        "today": today_count,
        "yesterday": yesterday_count,
        "today_in_page": today_in_page,
        "yesterday_in_page": yesterday_in_page,
    }
