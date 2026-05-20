import json
import datetime
from database import get_db
from app.repositories.business_repository import BusinessRepository
from app.repositories.raw_data_repository import RawDataRepository
from app.services.change_detector import ChangeDetector, ChangeResult, infer_change_type_from_bf_af
from app.services.scraper.mapper import map_row_fields, parse_datetime_fields
from app.services.scraper.persistence_notifier import trigger_sse_broadcast, trigger_backfill_thread

business_repo = BusinessRepository()
raw_repo = RawDataRepository()
detector = ChangeDetector()

def persist_single_crawl(service_id: str, new_data_rows: list) -> tuple[int, int]:
    """
    단건 크롤링 결과를 순차적으로 분석하여 DB에 반영합니다.
    - 기존 데이터와 델타(변동) 비교 수행
    - DB 커밋, 오늘 변동 시 SSE 알림 발행 및 백필 백그라운드 호출 트리거
    Returns: (실제 변경건수, 오늘 변동건수)
    """
    now = datetime.datetime.now().isoformat()
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    actually_changed = 0
    today_changed = 0
    all_lcns = []

    with get_db() as conn:
        for row in new_data_rows:
            fields = map_row_fields(service_id, row)
            if not fields or not fields["lcns_no"]:
                continue

            lcns_no = fields["lcns_no"]
            all_lcns.append(lcns_no)

            event_date, event_time, license_date, license_time = parse_datetime_fields(
                fields["event_date_raw"], fields["license_date"]
            )

            db_record = business_repo.get_business_by_license_no(lcns_no, conn=conn)

            if not db_record:
                # 신규 등록
                if fields.get("change_reason"):
                    infer_update_type, infer_update_detail = infer_change_type_from_bf_af(
                        fields["change_reason"], fields["change_before"], fields["change_after"]
                    )
                else:
                    infer_update_type = (
                        "신규등록" if license_date == event_date else "초기수집(과거변경있음)"
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
                    "collected_by": "rolling_scan",
                }
                business_repo.insert_business(record, conn=conn)
                raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)
                actually_changed += 1
                if event_date == today_str:
                    today_changed += 1

            else:
                # 중복 체크: 동일 (lcns_no, event_date) 이미 존재 -> 스킵
                prev_event_date = db_record.get("last_event_date", "")
                if prev_event_date == event_date:
                    prev_infer_type = db_record.get("infer_update_type", "")
                    is_mirror_upgrade = prev_infer_type == "mirror"

                    change: ChangeResult = detector.detect(
                        db_record=db_record,
                        new_rep_name=fields["representative_name"],
                        new_business_status=fields["business_status"],
                        new_business_name=fields["business_name"],
                        now=now,
                    )

                    should_update = (
                        change.is_updated
                        or (fields["industry_type"] and not db_record.get("industry_type"))
                        or is_mirror_upgrade
                    )

                    if should_update:
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
                            "infer_update_type": change.infer_update_type,
                            "infer_update_detail": change.infer_update_detail,
                            "last_event_date": event_date,
                            "last_event_time": event_time,
                            "license_time": license_time,
                            "updated_at": now,
                        }
                        business_repo.update_business(lcns_no, updates, conn=conn)
                        raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)
                        actually_changed += 1
                        if event_date == today_str:
                            today_changed += 1
                    continue

                # 변경 감지: event_date가 다름 -> 새로운 변동 이벤트
                is_mirror_upgrade = db_record.get("infer_update_type", "") == "mirror"
                is_event_date_changed = True

                change: ChangeResult = detector.detect(
                    db_record=db_record,
                    new_rep_name=fields["representative_name"],
                    new_business_status=fields["business_status"],
                    new_business_name=fields["business_name"],
                    now=now,
                )

                if change.infer_update_type:
                    resolved_infer_type = change.infer_update_type
                    resolved_infer_detail = change.infer_update_detail
                elif is_event_date_changed:
                    resolved_infer_type = "인허가변동"
                    resolved_infer_detail = f"변동일자: {prev_event_date} → {event_date}"
                elif is_mirror_upgrade:
                    resolved_infer_type = "변동확인"
                    resolved_infer_detail = None
                else:
                    resolved_infer_type = change.infer_update_type
                    resolved_infer_detail = change.infer_update_detail

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
                    "infer_update_type": resolved_infer_type,
                    "infer_update_detail": resolved_infer_detail,
                    "last_event_date": event_date,
                    "last_event_time": event_time,
                    "license_time": license_time,
                    "updated_at": now,
                }
                business_repo.update_business(lcns_no, updates, conn=conn)
                raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)
                actually_changed += 1
                if event_date == today_str:
                    today_changed += 1

        conn.commit()

    # SSE 발행 및 백필 트리거
    if today_changed > 0:
        trigger_sse_broadcast(today_changed, service_id)

    if all_lcns:
        unique_lcns = list(dict.fromkeys(lcns for lcns in all_lcns if lcns))
        trigger_backfill_thread(unique_lcns, service_id, "rolling_scan")

    return actually_changed, today_changed
