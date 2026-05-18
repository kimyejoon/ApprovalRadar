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

    ⚠️ 식품안전나라 인허가변경 API(I2859/I2861)는 "변경이력 로그" 구조로,
    아래 필드는 이 API 응답에 포함되지 않습니다:
      - 대표자명 (PRSDNT_NM)  → 개인정보 비공개, Backfill(I2500)로만 수집 가능
      - 영업상태 (BSN_STATE_NM) → 미제공
      - 인허가일자 (PRMS_DT)   → 미제공

    실제 API 공통 필드:
      LCNS_NO, BSSH_NM, SITE_ADDR, INDUTY_CD_NM, CHNG_DT, TELNO,
      CHNG_PRVNS (변경사유), CHNG_BF_CN (변경 전), CHNG_AF_CN (변경 후)
    """
    chng_prvns = row.get("CHNG_PRVNS", "")
    chng_af    = row.get("CHNG_AF_CN", "")

    # 지위승계(양도.양수 / 합병) 변경사유일 때만 CHNG_AF_CN = 신규 대표자명으로 확정
    # 그 외(주소변경, 상호변경 등)는 CHNG_AF_CN이 다른 내용이므로 I2500 백필로 보완
    is_succession = "지위승계" in chng_prvns
    rep_from_api = chng_af if is_succession else ""

    if service_id == "I2859":
        return {
            "lcns_no":             row.get("LCNS_NO", ""),
            "business_name":       row.get("BSSH_NM", ""),
            "address":             row.get("SITE_ADDR", ""),
            "representative_name": rep_from_api,  # 지위승계 시 즉시 추출, 나머지는 I2500 백필
            "business_status":     None,           # API 미제공
            "license_date":        "",              # PRMS_DT 미제공
            "phone_number":        row.get("TELNO", ""),
            "industry_type":       row.get("INDUTY_CD_NM", ""),
            "event_date_raw":      row.get("CHNG_DT", ""),
            "change_reason":       chng_prvns,
            "change_before":       row.get("CHNG_BF_CN", ""),
            "change_after":        chng_af,
        }
    elif service_id == "I2861":
        return {
            "lcns_no":             row.get("LCNS_NO", ""),
            "business_name":       row.get("BSSH_NM", ""),
            "address":             row.get("SITE_ADDR", "") or row.get("ADDR", ""),
            "representative_name": rep_from_api,  # 지위승계 시 즉시 추출, 나머지는 I2500 백필
            "business_status":     None,           # API 미제공
            "license_date":        "",              # PRMS_DT 미제공
            "phone_number":        row.get("TELNO", ""),
            "industry_type":       row.get("INDUTY_CD_NM", ""),
            "event_date_raw":      row.get("CHNG_DT", ""),
            "change_reason":       chng_prvns,
            "change_before":       row.get("CHNG_BF_CN", ""),
            "change_after":        chng_af,
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
                        prev_infer_type = db_record.get("infer_update_type", "")
                        prev_event_date = db_record.get("last_event_date", "")
                        is_mirror_upgrade = prev_infer_type == "mirror"  # CLI 초기 스캔 레코드
                        is_event_date_changed = prev_event_date and event_date and prev_event_date != event_date

                        change: ChangeResult = detector.detect(
                            db_record=db_record,
                            new_rep_name=fields["representative_name"],
                            new_business_status=fields["business_status"],
                            new_business_name=fields["business_name"],
                            now=now,
                        )

                        # ── mirror 레코드가 diff로 재발견되거나 이벤트일자 변경 시 업데이트 ──
                        # (1) mirror 레코드: CLI 초기 스캔값이 diff로 재발견 → '변동확인'으로 승급
                        # (2) last_event_date 변경: 동일 업소의 새로운 인허가 변동 이벤트 발생
                        should_update = (
                            change.is_updated
                            or (fields["industry_type"] and not db_record.get("industry_type"))
                            or is_mirror_upgrade
                            or is_event_date_changed
                        )

                        if should_update:
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


                conn.commit()

            total_elapsed = time.time() - start_time
            logger.info(
                f"✅ [{service_id} 총 소요시간: {total_elapsed:.2f}초] "
                f"모든 변경분({len(new_data_rows)}건)의 DB 업데이트 및 커밋 완료."
            )

            # ── SSE 즉시 발행 (백필 전) — count 포함 ────────────────────────
            # 프론트에서 count만큼 팝업을 생성하기 위해 변동 건수를 페이로드에 포함
            from app.core.events import broadcaster
            update_data = json.dumps(
                {"type": "UPDATE", "count": len(new_data_rows)}, ensure_ascii=False
            )
            broadcaster.broadcast_sync(update_data)

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


async def run_scraper_for_service_with_rows(service_id: str, new_data_rows: list):
    """
    [전략 C 전용] 외부에서 수집된 rows를 직접 주입하여 DB 저장 + SSE 발행 파이프라인 실행.
    scan_for_updates() 없이 이미 확보된 rows를 기존 scraper 파이프라인으로 처리.
    """
    import time
    import datetime
    from database import get_db, init_db
    from app.repositories.business_repository import BusinessRepository
    from app.repositories.raw_data_repository import RawDataRepository
    from app.services.change_detector import ChangeDetector

    init_db()
    business_repo = BusinessRepository()
    raw_repo = RawDataRepository()
    detector = ChangeDetector()
    now = datetime.datetime.now().isoformat()

    svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(service_id, service_id)
    logger.info(f"🆕 [전략C/{svc_name}] {len(new_data_rows)}건 DB 저장 시작...")

    with get_db() as conn:
        for row in new_data_rows:
            fields = _map_row_fields(service_id, row)
            if not fields or not fields["lcns_no"]:
                continue
            lcns_no = fields["lcns_no"]
            raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)

            event_date, event_time, license_date, license_time = _parse_datetime_fields(
                fields["event_date_raw"], fields["license_date"]
            )
            db_record = business_repo.get_business_by_license_no(lcns_no, conn=conn)
            if not db_record:
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
        conn.commit()

    logger.info(f"✅ [전략C/{svc_name}] {len(new_data_rows)}건 DB 저장 완료")

    # SSE 브로드캐스트
    from app.core.events import broadcaster
    update_data = json.dumps(
        {"type": "UPDATE", "message": "신규 업데이트가 발생했다"}, ensure_ascii=False
    )
    broadcaster.broadcast_sync(update_data)


if __name__ == "__main__":
    asyncio.run(run_all_scrapers())
