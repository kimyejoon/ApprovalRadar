from typing import Optional, Dict, Any
from app.core.logger import logger

def map_row_fields(service_id: str, row: dict) -> Optional[Dict[str, Any]]:
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


def parse_datetime_fields(event_date_raw: str, license_date_raw: str):
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
