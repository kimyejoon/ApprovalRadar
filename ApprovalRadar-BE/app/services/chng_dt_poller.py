"""
I2500 CHNG_DT 폴러 — 3-Way 전략의 세 번째 축.

매 5분 간격으로 I2500 서비스에 CHNG_DT=오늘 파라미터를 넣어
당일 변동된 업소 목록을 직접 조회합니다.

I2500은 I2861과 달리 CHNG_DT 필터가 실제 작동하므로,
오늘 변경된 레코드를 즉시 가져올 수 있습니다.

I2500 응답 필드:
  PRSDNT_NM, INDUTY_CD_NM, PRMS_DT, LCNS_NO, BSSH_NM, TELNO, ADDR
  (CHNG_DT 필드는 응답에 미포함 — 요청 파라미터로만 사용)

기존 I2861 Rolling Scan과 Tail Ping이 놓칠 수 있는
당일 변동분을 직접 감지하여 DB INSERT + SSE 발행합니다.

API 비용: 최대 5~6회/주기 (5000건 기준 5페이지)
"""
import asyncio
import datetime

from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from database import get_db

# I2500 서비스 ID (인허가변동 이력 — CHNG_DT 필터 작동)
SERVICE_ID = "I2500"
PAGE_SIZE = 1000
POLL_INTERVAL_MINUTES = 5

# I2500 → businesses 테이블 필드 매핑
# I2500은 I2861과 필드명이 다르지만 LCNS_NO는 동일
FIELD_MAP = {
    "LCNS_NO": "license_no",
    "BSSH_NM": "business_name",
    "ADDR": "address",
    "PRSDNT_NM": "representative_name",
    "TELNO": "phone_number",
    "INDUTY_CD_NM": "industry_type",
    "PRMS_DT": "license_date",  # 인허가일자
}


async def poll_today_changes(target_date: str = None):
    """
    I2500 CHNG_DT=오늘 조회 → DB에 없는 건만 INSERT.

    Args:
        target_date: 조회할 날짜 (YYYYMMDD). None이면 오늘.

    Returns:
        dict: {"total": API 전체, "new": 신규 INSERT, "skipped": 중복 스킵}
    """
    today_str = target_date or datetime.date.today().strftime("%Y%m%d")
    result = {"total": 0, "new": 0, "skipped": 0, "date": today_str}

    if ApiClient.is_exhausted():
        logger.debug("[CHNG_DT Poller] API 키 소진 → 스킵")
        return result

    if shutdown_event.is_set():
        return result

    try:
        async with ApiClient() as api_client:
            # ── Step 1: 전체 건수 확인 (1건 조회) ──
            res = await api_client.fetch_data(
                SERVICE_ID, 1, 1, CHNG_DT=today_str, timeout=10
            )

            if not res or SERVICE_ID not in res:
                logger.debug(f"[CHNG_DT Poller] I2500 응답 없음")
                return result

            block = res[SERVICE_ID]
            code = block.get("RESULT", {}).get("CODE", "")

            if code == "INFO-200":
                logger.info(f"[CHNG_DT Poller] CHNG_DT={today_str} 변동분 없음")
                return result

            if code != "INFO-000":
                logger.warning(f"[CHNG_DT Poller] 응답 코드: {code}")
                return result

            total = int(block.get("total_count", "0"))
            result["total"] = total
            logger.info(
                f"[CHNG_DT Poller] I2500 CHNG_DT={today_str} → "
                f"전체 {total:,}건 감지, 수집 시작..."
            )

            # ── Step 2: 전체 페이지 순회하여 수집 ──
            all_items = []
            start = 1
            while start <= total:
                end = min(start + PAGE_SIZE - 1, total)
                page_res = await api_client.fetch_data(
                    SERVICE_ID, start, end, CHNG_DT=today_str, timeout=15
                )

                if page_res and SERVICE_ID in page_res:
                    rows = page_res[SERVICE_ID].get("row", [])
                    all_items.extend(rows)
                    logger.info(
                        f"[CHNG_DT Poller] 페이지 {start}~{end}: {len(rows)}건"
                    )
                else:
                    logger.warning(f"[CHNG_DT Poller] 페이지 {start}~{end} 실패")

                start += PAGE_SIZE

                if shutdown_event.is_set():
                    break

            if not all_items:
                return result

            # ── Step 3: DB 중복 체크 (LCNS, CHNG_DT 쌍) ──
            lcns_list = [item.get("LCNS_NO", "") for item in all_items if item.get("LCNS_NO")]
            existing_pairs = set()

            with get_db() as conn:
                for i in range(0, len(lcns_list), 500):
                    batch = lcns_list[i:i + 500]
                    ph = ",".join(["?"] * len(batch))
                    rows = conn.execute(
                        f"SELECT license_no, last_event_date FROM businesses "
                        f"WHERE license_no IN ({ph})",
                        batch
                    ).fetchall()
                    for row in rows:
                        existing_pairs.add((row["license_no"], row["last_event_date"]))

            # ── Step 4: 신규 건만 필터 ──
            new_items = []
            for item in all_items:
                lcns = item.get("LCNS_NO", "")
                if not lcns:
                    continue
                # I2500 응답에는 CHNG_DT 필드가 없음 → 요청 파라미터의 날짜 사용
                pair = (lcns, today_str)
                if pair not in existing_pairs:
                    new_items.append(item)
                    existing_pairs.add(pair)  # 중복 방지

            result["skipped"] = len(all_items) - len(new_items)

            if not new_items:
                logger.info(
                    f"[CHNG_DT Poller] {len(all_items)}건 모두 이미 수집됨 "
                    f"→ Rolling Scan이 정상 작동 중 ✅"
                )
                return result

            # ── Step 5: I2500 → I2861 형식으로 변환하여 scraper 파이프라인 처리 ──
            mapped_rows = []
            for item in new_items:
                # I2861 형식으로 변환 (scraper가 기대하는 필드)
                i2861_row = {
                    "LCNS_NO": item.get("LCNS_NO", ""),
                    "BSSH_NM": item.get("BSSH_NM", ""),
                    "SITE_ADDR": item.get("ADDR", ""),
                    "PRSDNT_NM": item.get("PRSDNT_NM", ""),
                    "BSN_STATE_NM": None,  # I2500에 없는 필드
                    "PRMS_DT": item.get("PRMS_DT", ""),
                    "TELNO": item.get("TELNO", ""),
                    "INDUTY_CD_NM": item.get("INDUTY_CD_NM", ""),
                    "CHNG_DT": today_str,  # 요청 파라미터에서 사용
                    # I2861 추가 필드 (I2500에 없음)
                    "SITE_ADDR_RDN": item.get("ADDR", ""),
                }
                mapped_rows.append(i2861_row)

            logger.info(
                f"[CHNG_DT Poller] 🆕 DB 미수집 {len(new_items)}/{len(all_items)}건 "
                f"→ scraper 파이프라인 처리"
            )

            # scraper 파이프라인으로 위임
            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows("I2861", mapped_rows)
            result["new"] = len(new_items)

            logger.info(
                f"🔔 [CHNG_DT Poller] 완료: CHNG_DT={today_str} "
                f"전체 {total}건 중 신규 {len(new_items)}건 INSERT → SSE 발행"
            )

    except ApiKeysExhaustedError:
        logger.info("[CHNG_DT Poller] API 키 소진 → 다음 주기에 재시도")
    except Exception as e:
        logger.error(f"[CHNG_DT Poller] 오류: {e}", exc_info=True)

    return result


def run_chng_dt_poller():
    """스케줄러 동기 래퍼."""
    asyncio.run(poll_today_changes())
