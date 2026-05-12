import datetime
import json
import re
from typing import List

from database import init_db
from app.clients.foodsafety_api import ApiClient
from app.services.diff_crawler import DiffCrawlerEngine
from app.core.logger import logger

from app.repositories.business_repository import BusinessRepository
from app.repositories.raw_data_repository import RawDataRepository

def parse_representatives(rep_str: str) -> List[str]:
    """
    공동 대표자 파싱 로직
    예: '김**, 이**' -> ['김**', '이**']
    """
    if not rep_str:
        return []
    parts = re.split(r'[,/&]|및', rep_str)
    return [p.strip() for p in parts if p.strip()]

def run_scraper_job():
    logger.info("Starting DiffCrawler Delta Sync Job...")
    
    # DB 초기화 (테이블 없으면 생성, WAL 모드 적용 등)
    init_db()
    
    api_client = ApiClient()
    crawler = DiffCrawlerEngine(api_client=api_client)
    business_repo = BusinessRepository()
    raw_repo = RawDataRepository()
    
    try:
        new_data_rows = crawler.scan_for_updates()
        if not new_data_rows:
            logger.info("No new updates found.")
            return
            
        logger.info(f"Processing {len(new_data_rows)} new/updated records...")
        now = datetime.datetime.now().isoformat()
        
        from database import get_db
        with get_db() as conn:
            for row in new_data_rows:
                lcns_no = row.get("LCNS_NO")
                if not lcns_no:
                    continue
                    
                # 1. 원본 API 응답(JSON) DB 저장 (Repository 사용)
                raw_repo.insert_raw_data(lcns_no, json.dumps(row, ensure_ascii=False), now, conn=conn)
                
                # 2. Main 테이블(businesses) 파싱 준비
                bssh_nm = row.get("BSSH_NM", "")
                addr = row.get("LOCP_ADDR", "")
                rep_name = row.get("PRSDNT_NM", "")
                business_status = row.get("BSN_STATE_NM", "")
                license_date = row.get("PRMS_DT", "")
                phone_number = row.get("TELNO", "")
                last_updt = row.get("LAST_UPDT_DTM", "")
                cret_dtm = row.get("CRET_DTM", "")
                
                event_date = last_updt if last_updt else (cret_dtm if cret_dtm else license_date)
                if event_date and len(event_date) > 8:
                    event_date = event_date[:8]
                    
                db_record = business_repo.get_business_by_license_no(lcns_no, conn=conn)
                
                if not db_record:
                    # 신규 등록
                    record = {
                        "license_no": lcns_no,
                        "business_name": bssh_nm,
                        "address": addr,
                        "representative_name": rep_name,
                        "business_status": business_status,
                        "license_date": license_date,
                        "phone_number": phone_number,
                        "last_event_date": event_date
                    }
                    business_repo.insert_business(record, conn=conn)
                else:
                    prev_rep = db_record.get("representative_name", "")
                    prev_status = db_record.get("business_status", "")
                    rep_history = json.loads(db_record.get("representative_history") or "[]")
                    lic_history = json.loads(db_record.get("licensing_history") or "[]")
                    
                    is_updated = False
                    
                    # 대표자 변경 감지
                    old_reps = parse_representatives(prev_rep)
                    new_reps = parse_representatives(rep_name)
                    
                    if set(old_reps) != set(new_reps):
                        rep_history.append({
                            "date": now,
                            "prev": prev_rep,
                            "new": rep_name
                        })
                        is_updated = True
                        
                    # 영업 상태 변경 감지
                    if prev_status != business_status:
                        lic_history.append({
                            "date": now,
                            "type": "상태변경",
                            "prev": prev_status,
                            "new": business_status
                        })
                        is_updated = True
                        
                    if is_updated:
                        updates = {
                            "business_name": bssh_nm,
                            "address": addr,
                            "representative_name": rep_name,
                            "business_status": business_status,
                            "phone_number": phone_number,
                            "representative_history": json.dumps(rep_history, ensure_ascii=False),
                            "licensing_history": json.dumps(lic_history, ensure_ascii=False),
                            "last_event_date": event_date,
                            "updated_at": now
                        }
                        business_repo.update_business(lcns_no, updates, conn=conn)
            
            # 모든 처리가 끝난 후 커밋
            conn.commit()
        
        logger.info("Processing complete and committed to DB.")
            
    except Exception as e:
        logger.error(f"Error during scraper job: {e}")

if __name__ == "__main__":
    run_scraper_job()
