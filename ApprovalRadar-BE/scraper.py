import datetime
import json
import logging
import re
from typing import List

from database import get_db, init_db
from app.clients.foodsafety_api import ApiClient
from app.services.diff_crawler import DiffCrawlerEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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
    
    def log_cb(msg):
        logger.info(msg)
        
    api_client = ApiClient(log_callback=log_cb)
    crawler = DiffCrawlerEngine(api_client=api_client, log_callback=log_cb)
    
    try:
        new_data_rows = crawler.scan_for_updates()
        if not new_data_rows:
            logger.info("No new updates found.")
            return
            
        logger.info(f"Processing {len(new_data_rows)} new/updated records...")
        
        with get_db() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now().isoformat()
            
            for row in new_data_rows:
                lcns_no = row.get("LCNS_NO")
                if not lcns_no:
                    continue
                    
                # 1. 원본 API 응답(JSON) DB 저장 (요구사항 반영)
                cursor.execute('''
                    INSERT OR REPLACE INTO api_raw_data (license_no, raw_json, fetched_at)
                    VALUES (?, ?, ?)
                ''', (lcns_no, json.dumps(row, ensure_ascii=False), now))
                
                # 2. Main 테이블(businesses) 업데이트 로직
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
                    
                cursor.execute("SELECT * FROM businesses WHERE license_no = ?", (lcns_no,))
                db_record = cursor.fetchone()
                
                if not db_record:
                    # 신규 등록
                    cursor.execute('''
                        INSERT INTO businesses 
                        (license_no, business_name, address, representative_name, business_status, license_date, phone_number, last_event_date, is_new)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (lcns_no, bssh_nm, addr, rep_name, business_status, license_date, phone_number, event_date))
                else:
                    db_dict = dict(db_record)
                    prev_rep = db_dict["representative_name"]
                    prev_status = db_dict["business_status"]
                    rep_history = json.loads(db_dict["representative_history"] or "[]")
                    lic_history = json.loads(db_dict["licensing_history"] or "[]")
                    
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
                        cursor.execute('''
                            UPDATE businesses 
                            SET business_name = ?, address = ?, representative_name = ?, 
                                business_status = ?, phone_number = ?,
                                representative_history = ?, licensing_history = ?,
                                last_event_date = ?,
                                updated_at = ?, is_new = 1
                            WHERE license_no = ?
                        ''', (
                            bssh_nm, addr, rep_name, business_status, phone_number,
                            json.dumps(rep_history, ensure_ascii=False),
                            json.dumps(lic_history, ensure_ascii=False),
                            event_date,
                            now, lcns_no
                        ))
            
            conn.commit()
            logger.info("Processing complete and committed to DB.")
            
    except Exception as e:
        logger.error(f"Error during scraper job: {e}")

if __name__ == "__main__":
    run_scraper_job()
