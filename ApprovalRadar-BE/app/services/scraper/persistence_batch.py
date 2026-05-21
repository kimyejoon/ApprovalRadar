import json
import datetime
from database import get_db
from app.repositories.business_repository import BusinessRepository
from app.repositories.raw_data_repository import RawDataRepository
from app.services.change_detector import infer_change_type_from_bf_af
from app.core.logger import logger
from app.services.scraper.persistence_notifier import trigger_sse_broadcast, trigger_backfill_thread

business_repo = BusinessRepository()
raw_repo = RawDataRepository()

def persist_batch_crawl(service_id: str, mapped_rows: list, collected_by: str) -> dict:
    """
    배치 크롤링 결과를 최적화된 batch SELECT 및 bulk INSERT로 DB에 반영합니다.

    Returns: {
        "total_fetched": 조회 건수,
        "new_indexed": 신규 색인 건수,
        "skipped_dup": 미색인(중복 스킵) 건수,
        "today": 오늘 변동 건수 (신규 INSERT 기준),
        "yesterday": 어제 변동 건수 (신규 INSERT 기준),
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
        existing_pairs = set()
        for i in range(0, len(unique_lcns), 500):
            batch = unique_lcns[i:i+500]
            placeholders = ",".join(["?"] * len(batch))
            cursor = conn.execute(
                f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({placeholders})",
                batch
            )
            for r in cursor.fetchall():
                existing_pairs.add((r["license_no"], r["last_event_date"]))

        logger.info(
            f"  📋 batch SELECT 완료: {len(unique_lcns)}건 LCNS 조회, "
            f"기존 이력 {len(existing_pairs)}쌍"
        )

        for m in mapped_rows:
            fields = m["fields"]
            lcns_no = fields["lcns_no"]
            event_date = m["event_date"]
            event_time = m["event_time"]
            license_date = m["license_date"]
            license_time = m["license_time"]

            pair = (lcns_no, event_date)

            # 전체 조회 기준 오늘/어제 카운트 (신규+중복 불문)
            if event_date == today_str:
                today_in_page += 1
            elif event_date == yesterday_str:
                yesterday_in_page += 1

            if pair in existing_pairs:
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
            business_repo.insert_business(record, conn=conn)
            raw_repo.insert_raw_data(lcns_no, json.dumps(m["raw_row"], ensure_ascii=False), now, conn=conn)
            new_indexed += 1
            inserted_lcns_list.append(lcns_no)
            if event_date == today_str:
                today_count += 1
            elif event_date == yesterday_str:
                yesterday_count += 1
            existing_pairs.add(pair)

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
