import os
import sys
import time
import concurrent.futures
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import init_db, get_db
from app.clients.foodsafety_api import ApiClient
from app.core.logger import logger
from app.repositories.business_repository import BusinessRepository

def fill_missing_industry_types():
    logger.info("Starting Industry Type Backfill Job...")
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

    def process_license(lcns_no):
        nonlocal processed_count, success_count, fail_count
        
        try:
            # I2500은 1건씩 단건 조회 (LCNS_NO 조건 필터)
            # ApiClient에서 kwargs로 받은 LCNS_NO를 URL 파라미터로 붙여줌
            res = api_client.fetch_data("I2500", 1, 1000, LCNS_NO=lcns_no)
            
            if res and "I2500" in res:
                code = res["I2500"]["RESULT"]["CODE"]
                if code == "INFO-000":
                    rows = res["I2500"].get("row", [])
                    if rows:
                        # 동일 인허가번호 중 가장 최신 데이터 혹은 첫 번째 데이터 채택
                        industry_type = rows[0].get("INDUTY_CD_NM", "")
                        if industry_type:
                            business_repo.update_industry_type(lcns_no, industry_type)
                            with lock:
                                success_count += 1
                        else:
                            with lock:
                                fail_count += 1
                    else:
                        with lock:
                            fail_count += 1
                else:
                    with lock:
                        fail_count += 1
            else:
                with lock:
                    fail_count += 1
                    
        except Exception as e:
            logger.error(f"Failed to fetch or update {lcns_no}: {e}")
            with lock:
                fail_count += 1
                
        with lock:
            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_missing:
                logger.info(f"[진척도] {processed_count}/{total_missing} 처리 완료 (성공: {success_count}, 실패: {fail_count})")
        
        # Rate Limiting (WAF 차단 방지)
        time.sleep(0.1)

    # 동시 워커 수를 3개로 제한하여 차단을 회피
    # 3 * 0.1s delay = 약 10~15 req/sec
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(process_license, missing_licenses)
        
    logger.info(f"🎉 백필 작업 완료! 총 {processed_count}건 중 {success_count}건 성공, {fail_count}건 실패.")

if __name__ == "__main__":
    fill_missing_industry_types()
