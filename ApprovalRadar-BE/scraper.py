import asyncio
import datetime
import json
from typing import List, Optional, Dict, Any

from database import init_db
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.services.diff_crawler import DiffCrawlerEngine
from app.services.change_detector import ChangeDetector, ChangeResult
from app.core.logger import logger

from app.repositories.business_repository import BusinessRepository
from app.repositories.raw_data_repository import RawDataRepository

# 서비스별 크롤러 연속 실패 카운터 (3회 이상 실패 시 ALERT SSE)
_consecutive_failures: dict[str, int] = {}


# ─── 필드 매핑 ────────────────────────────────────────────────────────────────

def _map_row_fields(service_id: str, row: dict) -> Optional[Dict[str, Any]]:
    """
    서비스별 API 응답 row를 내부 공통 필드 dict로 변환합니다.
    지원하지 않는 service_id는 None을 반환합니다.
    """
    if service_id == "I2859":
        last_updt = row.get("LAST_UPDT_DTM", "")
        cret_dtm = row.get("CRET_DTM", "")
        license_date = row.get("PRMS_DT", "")
        event_date = last_updt or cret_dtm or license_date
        return {
            "lcns_no": row.get("LCNS_NO", ""),
            "business_name": row.get("BSSH_NM", ""),
            "address": row.get("LOCP_ADDR", ""),
            "representative_name": row.get("PRSDNT_NM", ""),
            "business_status": row.get("BSN_STATE_NM", ""),
            "license_date": license_date,
            "phone_number": row.get("TELNO", ""),
            "industry_type": row.get("INDUTY_CD_NM", ""),
            "event_date_raw": event_date,
        }
    elif service_id == "I2861":
        license_date = row.get("PRMS_DT", "")
        event_date = row.get("CHNG_DT", "") or license_date
        return {
            "lcns_no": row.get("LCNS_NO", ""),
            "business_name": row.get("BSSH_NM", ""),
            "address": row.get("SITE_ADDR") or row.get("ADDR", ""),
            "representative_name": row.get("PRSDNT_NM", ""),
            "business_status": None,  # I2861은 영업상태 미제공
            "license_date": license_date,
            "phone_number": row.get("TELNO", ""),
            "industry_type": row.get("INDUTY_CD_NM", ""),
            "event_date_raw": event_date,
        }
    else:
        logger.warning(f"Unknown service_id: {service_id}. Skipping row mapping.")
        return None


def _parse_datetime_fields(event_date_raw: str, license_date_raw: str):
    """날짜/시간 문자열을 date(8자리)와 time(6자리)로 분리합니다."""
    event_date, event_time = None, None
    if event_date_raw:
        normalized = str(event_date_raw).replace("-", "").replace(" ", "").replace(":", "")
        if len(normalized) >= 14:
            event_time = normalized[8:14]
        event_date = normalized[:8]

    license_date, license_time = None, None
    if license_date_raw:
        normalized = str(license_date_raw).replace("-", "").replace(" ", "").replace(":", "")
        if len(normalized) >= 14:
            license_time = normalized[8:14]
        license_date = normalized[:8]

    return event_date, event_time, license_date, license_time


# ─── 메인 스크래퍼 ─────────────────────────────────────────────────────────────

async def run_scraper_for_service(service_id: str):
    import time
    start_time = time.time()

    # 키 소진 상태 사전 체크
    if ApiClient.is_exhausted():
        logger.info(f"[{service_id}] API 키 소진 상태 → 스킵 (10분 후 Key Status 재조회 예정)")
        return

    logger.info(f"Starting DiffCrawler Delta Sync Job for {service_id}...")
    init_db()

    async with ApiClient() as api_client:
        crawler = DiffCrawlerEngine(api_client=api_client, service_id=service_id)
        business_repo = BusinessRepository()
        raw_repo = RawDataRepository()
        detector = ChangeDetector()

        try:
            new_data_rows = await crawler.scan_for_updates()
            # 성공 시 연속 실패 카운터 초기화
            _consecutive_failures[service_id] = 0
            if not new_data_rows:
                return

            logger.info(
                f"🚀 {len(new_data_rows)}건의 새로운 인허가 변경분이 {service_id}에서 감지되었습니다. "
                f"DB 업데이트를 시작합니다..."
            )
            now = datetime.datetime.now().isoformat()

            from database import get_db
            with get_db() as conn:
                for row in new_data_rows:
                    fields = _map_row_fields(service_id, row)
                    if not fields or not fields["lcns_no"]:
                        continue

                    lcns_no = fields["lcns_no"]

                    # 1. 원본 API 응답(JSON) DB 저장
                    raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)

                    # 2. 날짜/시간 필드 파싱
                    event_date, event_time, license_date, license_time = _parse_datetime_fields(
                        fields["event_date_raw"], fields["license_date"]
                    )

                    db_record = business_repo.get_business_by_license_no(lcns_no, conn=conn)

                    if not db_record:
                        # ── 신규 등록 ──────────────────────────────────────────
                        infer_update_type = (
                            "신규등록" if license_date == event_date else "초기수집(과거변경있음)"
                        )
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
                            "infer_update_detail": None,
                            "last_event_time": event_time,
                            "license_time": license_time,
                        }
                        business_repo.insert_business(record, conn=conn)

                    else:
                        # ── 변경 감지 ──────────────────────────────────────────
                        change: ChangeResult = detector.detect(
                            db_record=db_record,
                            new_rep_name=fields["representative_name"],
                            new_business_status=fields["business_status"],
                            new_business_name=fields["business_name"],
                            now=now,
                        )

                        if change.is_updated or (
                            fields["industry_type"] and not db_record.get("industry_type")
                        ):
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

                conn.commit()

            total_elapsed = time.time() - start_time
            logger.info(
                f"✅ [{service_id} 총 소요시간: {total_elapsed:.2f}초] "
                f"모든 변경분({len(new_data_rows)}건)의 DB 업데이트 및 커밋 완료."
            )

            # SSE 브로드캐스트
            from app.core.events import broadcaster
            update_data = json.dumps(
                {"type": "UPDATE", "message": "신규 업데이트가 발생했다"}, ensure_ascii=False
            )
            broadcaster.broadcast_sync(update_data)

            # 즉시 Backfill 트리거 (industry_type 누락 건)
            licenses_needing_industry = [
                row.get("LCNS_NO")
                for row in new_data_rows
                if row.get("LCNS_NO") and not row.get("INDUTY_CD_NM", "")
            ]
            if licenses_needing_industry:
                logger.info(
                    f"[즉시 Backfill 트리거] {len(licenses_needing_industry)}건의 신규 삽입 건에 "
                    f"세부업종 없음 → 즉시 Backfill 데몬 스레드 시작"
                )
                import threading
                from app.services.industry_filler import fill_industry_for_licenses
                threading.Thread(
                    target=lambda: asyncio.run(fill_industry_for_licenses(licenses_needing_industry)),
                    daemon=True,
                    name=f"ImmediateBackfillThread-{service_id}",
                ).start()

        except Exception as e:
            logger.error(f"❌ {service_id} 크롤러 스케줄 작업 중 치명적인 오류 발생: {e}")
            # 연속 실패 카운터 증가
            _consecutive_failures[service_id] = _consecutive_failures.get(service_id, 0) + 1
            fail_count = _consecutive_failures[service_id]
            if fail_count >= 5:
                try:
                    from app.core.events import broadcaster
                    svc_name = {
                        "I2859": "식품업소 인허가변경",
                        "I2861": "음식점업소 인허가변경",
                    }.get(service_id, service_id)
                    alert_msg = json.dumps({
                        "type": "ALERT",
                        "message": f"크롤러 연속 {fail_count}회 실패: {svc_name} 크롤러가 {fail_count}회 연속 오류를 발생했습니다."
                    }, ensure_ascii=False)
                    broadcaster.broadcast_sync(alert_msg)
                except Exception:
                    pass


async def run_all_scrapers():
    from app.core.config import settings
    services = getattr(settings, "SERVICES", ["I2859", "I2861"])
    for svc in services:
        await run_scraper_for_service(svc)


if __name__ == "__main__":
    asyncio.run(run_all_scrapers())
