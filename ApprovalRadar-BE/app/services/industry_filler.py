import os
import sys
import time
import random
import concurrent.futures
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import init_db, get_db
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.core.config import settings
from app.core.logger import logger
from app.repositories.business_repository import BusinessRepository

def fill_missing_industry_types():
    logger.info("Starting Industry Type Backfill Job...")

    # 키 소진 상태 사전 체크
    if ApiClient.is_exhausted():
        logger.info("[Backfill] API 키 소진 상태 → 백필 스킵 (자정 후 자동 재개)")
        return

    init_db()

    business_repo = BusinessRepository()
    api_client = ApiClient()

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
    lock = threading.Lock()
    stop_flag = threading.Event()  # 키 소진 시 전체 작업 중단용

    def process_license(lcns_no):
        nonlocal processed_count, success_count, fail_count

        if stop_flag.is_set():
            return  # 소진 신호 수신 시 즉시 건너뜀

        try:
            # I2500은 1건씩 단건 조회 (LCNS_NO 조건 필터)
            res = api_client.fetch_data("I2500", 1, 1000, LCNS_NO=lcns_no)

            if res and "I2500" in res:
                code = res["I2500"]["RESULT"]["CODE"]
                if code == "INFO-000":
                    rows = res["I2500"].get("row", [])
                    if rows:
                        industry_type = rows[0].get("INDUTY_CD_NM", "")
                        if industry_type:
                            business_repo.update_industry_type(lcns_no, industry_type)
                            with lock:
                                success_count += 1
                            logger.info(f"✅ {lcns_no} -> {industry_type} 업데이트 완료")
                        else:
                            with lock:
                                fail_count += 1
                            logger.info(f"⚠️ {lcns_no} -> 데이터는 있으나 세부업종 필드(INDUTY_CD_NM)가 비어있음")
                    else:
                        with lock:
                            fail_count += 1
                        logger.info(f"⚠️ {lcns_no} -> API 응답에 해당 데이터 없음")
                else:
                    with lock:
                        fail_count += 1
            else:
                with lock:
                    fail_count += 1

        except ApiKeysExhaustedError:
            # 키 소진 시 전체 백필 즉시 중단 (더 이상 개별 항목 시도하지 않음)
            logger.warning("[Backfill] API 키 소진 → 백필 작업 중단. 내일 자정 이후 자동 재개됩니다.")
            stop_flag.set()
            return
        except Exception as e:
            logger.error(f"Failed to fetch or update {lcns_no}: {e}")
            with lock:
                fail_count += 1

        with lock:
            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_missing:
                logger.info(f"[진척도] {processed_count}/{total_missing} 처리 완료 (성공: {success_count}, 실패: {fail_count})")

        # WAF 차단 방지 Jitter(무작위 지연) - 고정 간격은 봇 패턴으로 감지될 수 있음
        time.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

    # 단일 워커 순차 처리 (WAF 우회)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.map(process_license, missing_licenses)

    if stop_flag.is_set():
        logger.info(f"[Backfill] 키 소진으로 중단됨. {processed_count}/{total_missing}건 처리 (성공: {success_count})")
    else:
        logger.info(f"🎉 백필 작업 완료! 총 {processed_count}건 중 {success_count}건 성공, {fail_count}건 실패.")

if __name__ == "__main__":
    fill_missing_industry_types()
