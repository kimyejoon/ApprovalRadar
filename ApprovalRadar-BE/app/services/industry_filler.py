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
    I2500 API로 특정 업소의 세부업종 + 대표자 + 연락처 + 인허가일을 조회하여 DB에 업데이트합니다.

    I2500 제공 필드:
      - INDUTY_CD_NM : 세부업종
      - PRSDNT_NM    : 대표자 (기존 빈 필드만 채움)
      - TELNO        : 연락처 (기존 빈 필드만 채움)
      - PRMS_DT      : 최초인허가일 (None/미색인만 채움)

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
    license_date = rows[0].get("PRMS_DT", "")

    # 모두 빈값이면 업데이트할 것 없음
    if not industry_type and not representative_name and not phone_number and not license_date:
        return False

    business_repo.update_from_i2500(
        license_no=lcns_no,
        industry_type=industry_type,
        representative_name=representative_name,
        phone_number=phone_number,
        license_date=license_date,
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

    logger.info(f"총 {total_missing}건의 세부업종 누락 데이터를 발견했습니다. 병렬 백필을 시작합니다.")

    queue = asyncio.Queue()
    for lcns in missing_licenses:
        queue.put_nowait(lcns)

    results = {"success": 0, "fail": 0, "exhausted": False}
    results_lock = asyncio.Lock()

    # 동시 워커 수 설정
    n_workers = min(settings.SCAN_WORKERS, total_missing)
    if n_workers < 1:
        n_workers = 1

    async def worker():
        async with ApiClient() as api_client:
            while not queue.empty():
                if ApiClient.is_exhausted():
                    async with results_lock:
                        results["exhausted"] = True
                    break
                
                try:
                    lcns_no = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    updated = await _fetch_and_update_industry(api_client, lcns_no, business_repo)
                    async with results_lock:
                        if updated:
                            results["success"] += 1
                            logger.info(f"✅ {lcns_no} 세부업종 업데이트 완료")
                        else:
                            results["fail"] += 1
                            logger.info(f"⚠️ {lcns_no} → 세부업종 데이터 없음 또는 필드 비어있음")
                except ApiKeysExhaustedError:
                    async with results_lock:
                        results["exhausted"] = True
                    break
                except Exception as e:
                    async with results_lock:
                        results["fail"] += 1
                    logger.error(f"Failed to fetch or update {lcns_no}: {e}")
                finally:
                    queue.task_done()

                # 주기적으로 진행 상태 로그 출력 (100건 단위)
                async with results_lock:
                    processed = results["success"] + results["fail"]
                    if processed % 100 == 0 or processed == total_missing:
                        logger.info(
                            f"[진척도] {processed}/{total_missing} 처리 완료 "
                            f"(성공: {results['success']}, 실패: {results['fail']})"
                        )

                # WAF 차단 방지 Jitter
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    # 병렬 실행
    workers = [asyncio.create_task(worker()) for _ in range(n_workers)]
    await asyncio.gather(*workers)

    processed_count = results["success"] + results["fail"]
    logger.info(f"🎉 백필 작업 완료! 총 {processed_count}건 중 {results['success']}건 성공, {results['fail']}건 실패.")


# ─── 신규 삽입 건 즉시 백필 ───────────────────────────────────────────────────

async def fill_industry_for_licenses(license_nos: list[str]) -> None:
    """
    신규 삽입 건에 한정한 즉시(Immediate) 세부업종 병렬 Backfill.

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

    # 중복 라이선스 번호 제거
    unique_licenses = list(set(license_nos))
    logger.info(
        f"[즉시 Backfill] 신규 삽입 {len(unique_licenses)}건(원시 {len(license_nos)}건)에 대해 "
        f"세부업종 즉시 병렬 채우기 시작..."
    )
    
    business_repo = BusinessRepository()
    queue = asyncio.Queue()
    for lcns in unique_licenses:
        queue.put_nowait(lcns)

    results = {"success": 0, "fail": 0, "exhausted": False}
    results_lock = asyncio.Lock()

    # 동시 워커 수 설정
    n_workers = min(settings.SCAN_WORKERS, len(unique_licenses))
    if n_workers < 1:
        n_workers = 1

    async def worker():
        async with ApiClient() as api_client:
            while not queue.empty():
                if ApiClient.is_exhausted():
                    async with results_lock:
                        results["exhausted"] = True
                    break
                
                try:
                    lcns_no = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    updated = await _fetch_and_update_industry(api_client, lcns_no, business_repo)
                    async with results_lock:
                        if updated:
                            results["success"] += 1
                            logger.info(f"[즉시 Backfill] ✅ {lcns_no} 업데이트 완료")
                        else:
                            results["fail"] += 1
                            logger.debug(f"[즉시 Backfill] ⚠️ {lcns_no} → 세부업종 데이터 없음")
                except ApiKeysExhaustedError:
                    async with results_lock:
                        results["exhausted"] = True
                    break
                except Exception as e:
                    async with results_lock:
                        results["fail"] += 1
                    logger.error(f"[즉시 Backfill] ❌ {lcns_no} 처리 실패: {e}")
                finally:
                    queue.task_done()

                # WAF 차단 방지 Jitter
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    # 병렬 실행
    workers = [asyncio.create_task(worker()) for _ in range(n_workers)]
    await asyncio.gather(*workers)

    if results["exhausted"]:
        left = len(unique_licenses) - results["success"] - results["fail"]
        logger.warning(
            f"[즉시 Backfill] API 키 소진으로 일부 작업 중단. "
            f"잔여 {left}건은 6시간 주기 backfill_job에서 재시도됩니다."
        )

    logger.info(
        f"[즉시 Backfill] 완료. 총 {len(unique_licenses)}건 중 "
        f"성공: {results['success']}건, 실패: {results['fail']}건"
    )


if __name__ == "__main__":
    asyncio.run(fill_missing_industry_types())
