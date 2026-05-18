import asyncio
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import init_db, get_db
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.core.config import settings
from app.core.logger import logger
from app.repositories.business_repository import BusinessRepository


# ─── 공통 헬퍼 ────────────────────────────────────────────────────────────────

async def _fetch_and_update_industry(
    api_client: ApiClient,
    lcns_no: str,
    business_repo: BusinessRepository,
) -> bool:
    """
    I2500 API로 특정 업소의 세부업종 + 대표자 + 연락처를 조회하여 DB에 업데이트합니다.

    I2500 제공 필드:
      - INDUTY_CD_NM : 세부업종
      - PRSDNT_NM    : 대표자 (기존 빈 필드만 채움)
      - TELNO        : 연락처 (기존 빈 필드만 채움)

    Returns:
        True  = 1개 이상 필드 업데이트 성공
        False = 데이터 없음
    Raises:
        ApiKeysExhaustedError: 키 소진 시 상위로 전파
    """
    res = await api_client.fetch_data("I2500", 1, 1000, LCNS_NO=lcns_no)
    if not res or "I2500" not in res:
        return False

    block = res["I2500"]
    if block.get("RESULT", {}).get("CODE") != "INFO-000":
        return False

    rows = block.get("row", [])
    if not rows:
        return False

    industry_type = rows[0].get("INDUTY_CD_NM", "")
    representative_name = rows[0].get("PRSDNT_NM", "")
    phone_number = rows[0].get("TELNO", "")

    # 모두 빈값이면 업데이트할 것 없음
    if not industry_type and not representative_name and not phone_number:
        return False

    business_repo.update_from_i2500(
        license_no=lcns_no,
        industry_type=industry_type,
        representative_name=representative_name,
        phone_number=phone_number,
    )
    return True


# ─── 전체 누락 건 백필 ────────────────────────────────────────────────────────

async def fill_missing_industry_types():
    logger.info("Starting Industry Type Backfill Job...")

    if ApiClient.is_exhausted():
        logger.info("[Backfill] API 키 소진 상태 → 백필 스킵 (자정 후 자동 재개)")
        return

    init_db()
    business_repo = BusinessRepository()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT license_no FROM businesses WHERE industry_type IS NULL OR industry_type = ''")
        missing_records = cursor.fetchall()

    missing_licenses = [row["license_no"] for row in missing_records]
    total_missing = len(missing_licenses)

    if total_missing == 0:
        logger.info("모든 업소의 세부업종이 이미 채워져 있습니다. 작업을 종료합니다.")
        return

    logger.info(f"총 {total_missing}건의 세부업종 누락 데이터를 발견했습니다. 백필을 시작합니다.")

    processed_count = 0
    success_count = 0
    fail_count = 0

    async with ApiClient() as api_client:
        for lcns_no in missing_licenses:
            if ApiClient.is_exhausted():
                logger.warning("[Backfill] API 키 소진 → 백필 작업 중단. 내일 자정 이후 자동 재개됩니다.")
                break

            try:
                updated = await _fetch_and_update_industry(api_client, lcns_no, business_repo)
                if updated:
                    success_count += 1
                    logger.info(f"✅ {lcns_no} 세부업종 업데이트 완료")
                else:
                    fail_count += 1
                    logger.info(f"⚠️ {lcns_no} → 세부업종 데이터 없음 또는 필드 비어있음")

            except ApiKeysExhaustedError:
                logger.warning("[Backfill] API 키 소진 → 백필 작업 중단. 내일 자정 이후 자동 재개됩니다.")
                break
            except Exception as e:
                logger.error(f"Failed to fetch or update {lcns_no}: {e}")
                fail_count += 1

            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_missing:
                logger.info(
                    f"[진척도] {processed_count}/{total_missing} 처리 완료 "
                    f"(성공: {success_count}, 실패: {fail_count})"
                )

            # WAF 차단 방지 Jitter
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    logger.info(f"🎉 백필 작업 완료! 총 {processed_count}건 중 {success_count}건 성공, {fail_count}건 실패.")


# ─── 신규 삽입 건 즉시 백필 ───────────────────────────────────────────────────

async def fill_industry_for_licenses(license_nos: list[str]) -> None:
    """
    신규 삽입 건에 한정한 즉시(Immediate) 세부업종 Backfill.

    scraper.py에서 신규 Row를 DB에 삽입한 직후 호출되어, industry_type이 비어있는
    license_no 목록을 대상으로 I2500 API를 호출하여 세부업종을 즉시 채웁니다.
    - 전체 DB를 재조회하지 않고 대상 license_no만 처리 (효율적)
    - 키 소진/네트워크 오류 발생 시 6시간 주기 backfill_job에서 자동 재시도됨
    """
    if not license_nos:
        return

    if ApiClient.is_exhausted():
        logger.info(
            f"[즉시 Backfill] API 키 소진 → 스킵 "
            f"({len(license_nos)}건은 6시간 주기 backfill_job에서 재시도됩니다)"
        )
        return

    logger.info(f"[즉시 Backfill] 신규 삽입 {len(license_nos)}건에 대해 세부업종 즉시 채우기 시작...")
    business_repo = BusinessRepository()
    success_count = 0
    fail_count = 0

    async with ApiClient() as api_client:
        for lcns_no in license_nos:
            try:
                updated = await _fetch_and_update_industry(api_client, lcns_no, business_repo)
                if updated:
                    success_count += 1
                    logger.info(f"[즉시 Backfill] ✅ {lcns_no} 업데이트 완료")
                else:
                    fail_count += 1
                    logger.debug(f"[즉시 Backfill] ⚠️ {lcns_no} → 세부업종 데이터 없음")

            except ApiKeysExhaustedError:
                logger.warning(
                    f"[즉시 Backfill] API 키 소진 → 작업 중단. "
                    f"잔여 {len(license_nos) - success_count - fail_count}건은 "
                    f"6시간 주기 backfill_job에서 재시도됩니다."
                )
                break
            except Exception as e:
                fail_count += 1
                logger.error(f"[즉시 Backfill] ❌ {lcns_no} 처리 실패: {e}")

            # WAF 차단 방지 Jitter
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    logger.info(
        f"[즉시 Backfill] 완료. 총 {len(license_nos)}건 중 "
        f"성공: {success_count}건, 실패: {fail_count}건"
    )


if __name__ == "__main__":
    asyncio.run(fill_missing_industry_types())
