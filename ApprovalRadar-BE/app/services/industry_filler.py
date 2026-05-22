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
    db_lock: asyncio.Lock,
) -> bool:
    """
    I2500 API로 특정 업소의 세부업종 + 대표자 + 연락처를 조회하여 DB에 업데이트합니다.

    I2500 제공 필드 (PRMS_DT 인허가일자는 지금당장 필요 없어 수집 제외):
      - INDUTY_CD_NM : 세부업종
      - PRSDNT_NM    : 대표자 (기존 빈 필드만 쇼우)
      - TELNO        : 연락처 (기존 빈 필드만 쇼우)

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

    # SQLite 스레드/태스크 간 동시 쓰기 경합 방지
    async with db_lock:
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

    logger.info(f"총 {total_missing}건의 세부업종 누락 데이터를 발견했습니다. 병렬 백필을 시작합니다.")

    queue = asyncio.Queue()
    for lcns in missing_licenses:
        queue.put_nowait(lcns)

    results = {"success": 0, "fail": 0, "exhausted": False}
    results_lock = asyncio.Lock()
    db_lock = asyncio.Lock()

    # 동시 워커 수 설정
    n_workers = min(settings.SCAN_WORKERS, total_missing)
    if n_workers < 1:
        n_workers = 1

    # 워커별 ApiClient 생성 및 분산된 시작 키 할당 (WAF 세마포어 병목 방지)
    worker_clients = [ApiClient() for _ in range(n_workers)]
    n_keys = len(settings.API_KEYS)
    if n_keys > 0:
        for i, wc in enumerate(worker_clients):
            wc.key_manager.current_key_idx = i % n_keys

    async def worker(api_client: ApiClient, worker_id: int):
        try:
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
                    updated = await _fetch_and_update_industry(api_client, lcns_no, business_repo, db_lock)
                    async with results_lock:
                        if updated:
                            results["success"] += 1
                            logger.info(f"(W{worker_id}) ✅ {lcns_no} 세부업종 업데이트 완료")
                        else:
                            results["fail"] += 1
                            logger.info(f"(W{worker_id}) ⚠️ {lcns_no} → 세부업종 데이터 없음 또는 필드 비어있음")
                except ApiKeysExhaustedError:
                    async with results_lock:
                        results["exhausted"] = True
                    break
                except Exception as e:
                    async with results_lock:
                        results["fail"] += 1
                    logger.error(f"(W{worker_id}) Failed to fetch or update {lcns_no}: {e}")
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
        finally:
            await api_client.aclose()

    # 병렬 실행
    workers = [asyncio.create_task(worker(wc, i + 1)) for i, wc in enumerate(worker_clients)]
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
    unique_licenses = list(dict.fromkeys(license_nos))  # 순서 유지된 dedupe

    # ── DB 사전 확인: 대표자명이 이미 있는 라이선스는 I2500 호출 불필요 ──
    if unique_licenses:
        with __import__("database").get_db() as _conn:
            _placeholders = ",".join(["?"] * len(unique_licenses))
            _cursor = _conn.execute(
                f"SELECT license_no FROM businesses "
                f"WHERE license_no IN ({_placeholders}) "
                f"AND (representative_name IS NOT NULL AND representative_name != '')",
                unique_licenses
            )
            _already_filled = {r["license_no"] for r in _cursor.fetchall()}
        unique_licenses = [l for l in unique_licenses if l not in _already_filled]
        if _already_filled:
            logger.info(
                f"[즉시 Backfill] {len(_already_filled)}건은 대표자명 이미 확보 → I2500 스킵, "
                f"잔여 {len(unique_licenses)}건 보완 실행"
            )

    if not unique_licenses:
        logger.info("[즉시 Backfill] 모든 대상이 이미 대표자명 보유 → I2500 호출 전량 스킵")
        return

    logger.info(
        f"[즉시 Backfill] 신규 삽입 {len(unique_licenses)}건(원시 {len(license_nos)}건)에 대해 "
        f"세부업종 즉시 병렬 쇼우기 시작..."
    )
    
    business_repo = BusinessRepository()
    queue = asyncio.Queue()
    for lcns in unique_licenses:
        queue.put_nowait(lcns)

    results = {"success": 0, "fail": 0, "exhausted": False}
    results_lock = asyncio.Lock()
    db_lock = asyncio.Lock()

    # 동시 워커 수 설정
    n_workers = min(settings.SCAN_WORKERS, len(unique_licenses))
    if n_workers < 1:
        n_workers = 1

    # 워커별 ApiClient 생성 및 분산된 시작 키 할당 (WAF 세마포어 병목 방지)
    worker_clients = [ApiClient() for _ in range(n_workers)]
    n_keys = len(settings.API_KEYS)
    if n_keys > 0:
        for i, wc in enumerate(worker_clients):
            wc.key_manager.current_key_idx = i % n_keys

    async def worker(api_client: ApiClient, worker_id: int):
        try:
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
                    updated = await _fetch_and_update_industry(api_client, lcns_no, business_repo, db_lock)
                    async with results_lock:
                        if updated:
                            results["success"] += 1
                            logger.info(f"[즉시 Backfill] (W{worker_id}) ✅ {lcns_no} 업데이트 완료")
                        else:
                            results["fail"] += 1
                            logger.debug(f"[즉시 Backfill] (W{worker_id}) ⚠️ {lcns_no} → 세부업종 데이터 없음")
                except ApiKeysExhaustedError:
                    async with results_lock:
                        results["exhausted"] = True
                    break
                except Exception as e:
                    async with results_lock:
                        results["fail"] += 1
                    logger.error(f"[즉시 Backfill] (W{worker_id}) ❌ {lcns_no} 처리 실패: {e}")
                finally:
                    queue.task_done()

                # WAF 차단 방지 Jitter
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
        finally:
            await api_client.aclose()

    # 병렬 실행
    workers = [asyncio.create_task(worker(wc, i + 1)) for i, wc in enumerate(worker_clients)]
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
