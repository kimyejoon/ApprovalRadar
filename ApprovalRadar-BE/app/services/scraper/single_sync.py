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

# 서비스별 크롤러 연속 실패 카운터 (3회 이상 실패 시 ALERT SSE)
_consecutive_failures: dict[str, int] = {}

async def run_scraper_for_service(service_id: str):
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

            svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(service_id, service_id)
            logger.info(
                f"🆕 [{svc_name}] 신규 인허가 변동분 {len(new_data_rows)}건 발견! DB 저장 시작..."
            )
            # 발견된 건 요약 (업소명 + 인허가번호)
            for i, row in enumerate(new_data_rows[:10]):  # 최대 10건만 요약 표시
                biz_name = row.get("BSSH_NM") or row.get("BSSH_NM_INFO") or "업소명미상"
                lcns = row.get("LCNS_NO") or "인허가번호미상"
                logger.info(f"   └ [{i+1}] {biz_name} ({lcns})")
            if len(new_data_rows) > 10:
                logger.info(f"   └ ... 외 {len(new_data_rows)-10}건")
            now = datetime.datetime.now().isoformat()
            today_str = datetime.datetime.now().strftime("%Y%m%d")

            actually_changed = 0  # 실제 DB 변경 건수 (로그용)
            today_changed = 0    # 오늘 변동분만 (SSE 발행 기준)
            with get_db() as conn:
                for row in new_data_rows:
                    fields = _map_row_fields(service_id, row)
                    if not fields or not fields["lcns_no"]:
                        continue

                    lcns_no = fields["lcns_no"]

                    # 2. 날짜/시간 필드 파싱
                    event_date, event_time, license_date, license_time = _parse_datetime_fields(
                        fields["event_date_raw"], fields["license_date"]
                    )

                    db_record = business_repo.get_business_by_license_no(lcns_no, conn=conn)

                    if not db_record:
                        # ── 신규 등록 ──────────────────────────────────────────
                        # BF/AF 기반 스마트 추론 (CHNG_PRVNS 있을 때)
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
                        # 1. 원본 API 응답(JSON) DB 저장
                        raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)
                        actually_changed += 1
                        if event_date == today_str:
                            today_changed += 1

                    else:
                        # ── 중복 체크: 동일 (lcns_no, event_date) 이미 존재 → 스킵 ──
                        prev_event_date = db_record.get("last_event_date", "")
                        if prev_event_date == event_date:
                            # 이미 수집된 레코드 → 변경 감지만 수행
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
                            # else: 동일 event_date + 변경 없음 → 완전 스킵 (SSE 미발행)
                            continue

                        # ── 변경 감지: event_date가 다름 → 새로운 변동 이벤트 ──
                        is_mirror_upgrade = db_record.get("infer_update_type", "") == "mirror"
                        is_event_date_changed = True

                        change: ChangeResult = detector.detect(
                            db_record=db_record,
                            new_rep_name=fields["representative_name"],
                            new_business_status=fields["business_status"],
                            new_business_name=fields["business_name"],
                            now=now,
                        )

                        # infer_update_type 결정
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

            total_elapsed = time.time() - start_time
            logger.info(
                f"✅ [{service_id} 총 소요시간: {total_elapsed:.2f}초] "
                f"전체 {len(new_data_rows)}건 중 실제 변경 {actually_changed}건 DB 커밋 완료."
            )

            # ── SSE 즉시 발행 — 실제 변경 건수만 ────────────────────────
            # 이미 수집된 레코드가 반복 반환되어도 중복 SSE 발행 방지
            if today_changed > 0:
                from app.core.events import broadcaster
                update_data = json.dumps(
                    {"type": "UPDATE", "count": today_changed}, ensure_ascii=False
                )
                broadcaster.broadcast_sync(update_data)
                logger.info(
                    f"🔔 [{service_id}] 오늘 변동분 {today_changed}건 감지 → SSE 발행!"
                )

            # ── I2500 백필 (daemon thread) — SSE 발행 후 비동기 실행 ────────────
            # 동일 LCNS_NO 중복 제거 (같은 업소의 여러 변동분은 1회만 조회)
            # dict.fromkeys: 순서 보존 + 중복 제거
            all_lcns = list(dict.fromkeys(
                row.get("LCNS_NO")
                for row in new_data_rows
                if row.get("LCNS_NO")
            ))
            if all_lcns:
                logger.info(
                    f"[Backfill] {len(all_lcns)}건 I2500 백필 → 백그라운드 시작 "
                    f"(대표자+세부업종+연락처, SSE는 이미 발행 완료)"
                )
                import threading
                from app.services.industry_filler import fill_industry_for_licenses
                threading.Thread(
                    target=lambda lcns=all_lcns: asyncio.run(fill_industry_for_licenses(lcns)),
                    daemon=True,
                    name=f"BackfillThread-{service_id}",
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
