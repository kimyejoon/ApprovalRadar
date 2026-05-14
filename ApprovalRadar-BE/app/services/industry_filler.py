import asyncio
import os
import sys
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import init_db, get_db
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.core.config import settings
from app.core.logger import logger
from app.repositories.business_repository import BusinessRepository


async def fill_missing_industry_types():
    logger.info("Starting Industry Type Backfill Job...")

    # 키 소진 상태 사전 체크
    if ApiClient.is_exhausted():
        logger.info("[Backfill] API 키 소진 상태 → 백필 스킵 (자정 후 자동 재개)")
        return

    init_db()

    business_repo = BusinessRepository()

    # 누락된 레코드 조회
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

    # ✅ async with 컨텍스트 매니저로 AsyncClient 세션 자동 종료 보장
    async with ApiClient() as api_client:
        for lcns_no in missing_licenses:
            if ApiClient.is_exhausted():
                logger.warning("[Backfill] API 키 소진 → 백필 작업 중단. 내일 자정 이후 자동 재개됩니다.")
                break

            try:
                # I2500은 1건씩 단건 조회 (LCNS_NO 조건 필터)
                res = await api_client.fetch_data("I2500", 1, 1000, LCNS_NO=lcns_no)

                if res and "I2500" in res:
                    code = res["I2500"]["RESULT"]["CODE"]
                    if code == "INFO-000":
                        rows = res["I2500"].get("row", [])
                        if rows:
                            industry_type = rows[0].get("INDUTY_CD_NM", "")
                            if industry_type:
                                business_repo.update_industry_type(lcns_no, industry_type)
                                success_count += 1
                                logger.info(f"✅ {lcns_no} -> {industry_type} 업데이트 완료")
                            else:
                                fail_count += 1
                                logger.info(f"⚠️ {lcns_no} -> 데이터는 있으나 세부업종 필드(INDUTY_CD_NM)가 비어있음")
                        else:
                            fail_count += 1
                            logger.info(f"⚠️ {lcns_no} -> API 응답에 해당 데이터 없음")
                    else:
                        fail_count += 1
                else:
                    fail_count += 1

            except ApiKeysExhaustedError:
                logger.warning("[Backfill] API 키 소진 → 백필 작업 중단. 내일 자정 이후 자동 재개됩니다.")
                break
            except Exception as e:
                logger.error(f"Failed to fetch or update {lcns_no}: {e}")
                fail_count += 1

            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_missing:
                logger.info(f"[진척도] {processed_count}/{total_missing} 처리 완료 (성공: {success_count}, 실패: {fail_count})")

            # WAF 차단 방지 Jitter(무작위 지연) - 고정 간격은 봇 패턴으로 감지될 수 있음
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    logger.info(f"🎉 백필 작업 완료! 총 {processed_count}건 중 {success_count}건 성공, {fail_count}건 실패.")


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
            f"[즉시 Backfill] API 키 소진 → 스킵 ({len(license_nos)}건은 6시간 주기 backfill_job에서 재시도됩니다)"
        )
        return

    logger.info(f"[즉시 Backfill] 신규 삽입 {len(license_nos)}건에 대해 세부업종 즉시 채우기 시작...")
    business_repo = BusinessRepository()
    success_count = 0
    fail_count = 0

    async with ApiClient() as api_client:
        for lcns_no in license_nos:
            try:
                res = await api_client.fetch_data("I2500", 1, 1000, LCNS_NO=lcns_no)
                if res and "I2500" in res:
                    code = res["I2500"]["RESULT"]["CODE"]
                    if code == "INFO-000":
                        rows = res["I2500"].get("row", [])
                        if rows:
                            industry_type = rows[0].get("INDUTY_CD_NM", "")
                            if industry_type:
                                business_repo.update_industry_type(lcns_no, industry_type)
                                success_count += 1
                                logger.info(f"[즉시 Backfill] ✅ {lcns_no} → {industry_type}")
                            else:
                                fail_count += 1
                                logger.debug(f"[즉시 Backfill] ⚠️ {lcns_no} → INDUTY_CD_NM 필드 비어있음")
                        else:
                            fail_count += 1
                            logger.debug(f"[즉시 Backfill] ⚠️ {lcns_no} → I2500 응답에 데이터 없음")
                    else:
                        fail_count += 1
                else:
                    fail_count += 1
            except ApiKeysExhaustedError:
                logger.warning(
                    f"[즉시 Backfill] API 키 소진 → 작업 중단. "
                    f"잔여 {len(license_nos) - success_count - fail_count}건은 6시간 주기 backfill_job에서 재시도됩니다."
                )
                break
            except Exception as e:
                fail_count += 1
                logger.error(f"[즉시 Backfill] ❌ {lcns_no} 처리 실패: {e}")

            # WAF 차단 방지 Jitter
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    logger.info(
        f"[즉시 Backfill] 완료. 총 {len(license_nos)}건 중 성공: {success_count}건, 실패: {fail_count}건"
    )


if __name__ == "__main__":
    asyncio.run(fill_missing_industry_types())
