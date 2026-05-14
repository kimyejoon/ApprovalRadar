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

def run_scraper_for_service(service_id: str):
    import time
    start_time = time.time()
    logger.info(f"Starting DiffCrawler Delta Sync Job for {service_id}...")
    
    # DB 초기화 (테이블 없으면 생성, WAL 모드 적용 등)
    init_db()
    
    api_client = ApiClient()
    crawler = DiffCrawlerEngine(api_client=api_client, service_id=service_id)
    business_repo = BusinessRepository()
    raw_repo = RawDataRepository()
    
    try:
        new_data_rows = crawler.scan_for_updates()
        if not new_data_rows:
            # 이미 crawler 내부에서 소요시간이 찍히므로 여기선 중복 메시지 생략 또는 최소화
            return
            
        logger.info(f"🚀 {len(new_data_rows)}건의 새로운 인허가 변경분이 {service_id}에서 감지되었습니다. DB 업데이트를 시작합니다...")
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
                if service_id == "I2859":
                    bssh_nm = row.get("BSSH_NM", "")
                    addr = row.get("LOCP_ADDR", "")
                    rep_name = row.get("PRSDNT_NM", "")
                    business_status = row.get("BSN_STATE_NM", "")
                    license_date = row.get("PRMS_DT", "")
                    phone_number = row.get("TELNO", "")
                    last_updt = row.get("LAST_UPDT_DTM", "")
                    cret_dtm = row.get("CRET_DTM", "")
                    event_date = last_updt if last_updt else (cret_dtm if cret_dtm else license_date)
                    industry_type = row.get("INDUTY_CD_NM", "")
                elif service_id == "I2500":
                    bssh_nm = row.get("BSSH_NM", "")
                    addr = row.get("SITE_ADDR") or row.get("ADDR", "")
                    rep_name = row.get("PRSDNT_NM", "")
                    business_status = None # 데이터 무결성을 위해 비워둠
                    license_date = row.get("PRMS_DT", "")
                    phone_number = row.get("TELNO", "")
                    event_date = row.get("CHNG_DT", "") or license_date
                    industry_type = row.get("INDUTY_CD_NM", "")
                else:
                    logger.warning(f"Unknown service_id: {service_id}. Skipping row mapping.")
                    continue

                event_time = None
                if event_date:
                    orig_event = str(event_date).replace("-", "").replace(" ", "").replace(":", "")
                    if len(orig_event) >= 14:
                        event_time = orig_event[8:14]
                    event_date = orig_event[:8]
                        
                license_time = None
                if license_date:
                    orig_license = str(license_date).replace("-", "").replace(" ", "").replace(":", "")
                    if len(orig_license) >= 14:
                        license_time = orig_license[8:14]
                    license_date = orig_license[:8]
                db_record = business_repo.get_business_by_license_no(lcns_no, conn=conn)
                
                if not db_record:
                    # 신규 등록
                    infer_update_type = "신규등록" if license_date == event_date else "초기수집(과거변경있음)"
                    infer_update_detail = None
                    record = {
                        "license_no": lcns_no,
                        "business_name": bssh_nm,
                        "address": addr,
                        "representative_name": rep_name,
                        "business_status": business_status,
                        "license_date": license_date,
                        "phone_number": phone_number,
                        "industry_type": industry_type,
                        "last_event_date": event_date,
                        "infer_update_type": infer_update_type,
                        "infer_update_detail": infer_update_detail,
                        "last_event_time": event_time,
                        "license_time": license_time
                    }
                    business_repo.insert_business(record, conn=conn)
                else:
                    prev_rep = db_record.get("representative_name", "")
                    prev_status = db_record.get("business_status", "")
                    prev_name = db_record.get("business_name", "")
                    rep_history = json.loads(db_record.get("representative_history") or "[]")
                    lic_history = json.loads(db_record.get("licensing_history") or "[]")
                    
                    is_updated = False
                    
                    update_type = None
                    prev_business_status_val = None
                    prev_representative_name_val = None
                    prev_business_name_val = None
                    
                    # 대표자 변경 감지
                    old_reps = parse_representatives(prev_rep)
                    new_reps = parse_representatives(rep_name)
                    
                    if rep_name and set(old_reps) != set(new_reps):
                        update_type = "대표자변경"
                        prev_representative_name_val = prev_rep
                        rep_history.append({
                            "date": now,
                            "prev": prev_rep,
                            "new": rep_name
                        })
                        is_updated = True
                        
                    # 영업 상태 변경 감지
                    if business_status is not None and prev_status != business_status:
                        update_type = "상태변경"
                        prev_business_status_val = prev_status
                        lic_history.append({
                            "date": now,
                            "type": "상태변경",
                            "prev": prev_status,
                            "new": business_status
                        })
                        is_updated = True
                        
                    # 업소명 변경 감지 (API에 명칭 변경이 있는 경우 등)
                    if prev_name != bssh_nm:
                        update_type = "명칭변경"
                        prev_business_name_val = prev_name
                        is_updated = True
                        
                    # infer_update_type 결정 로직
                    infer_update_type = None
                    infer_update_detail = None
                    if update_type == "대표자변경":
                        infer_update_type = "대표자변경"
                        infer_update_detail = prev_representative_name_val if prev_representative_name_val else None
                    elif update_type == "명칭변경":
                        infer_update_type = "명칭변경"
                        infer_update_detail = prev_business_name_val if prev_business_name_val else None
                    elif update_type == "상태변경":
                        infer_update_type = "상태변경"
                        infer_update_detail = prev_business_status_val if prev_business_status_val else None

                    if is_updated or (industry_type and not db_record.get("industry_type")):
                        updates = {
                            "business_name": bssh_nm,
                            "address": addr,
                            "representative_name": rep_name,
                            "business_status": business_status if business_status is not None else prev_status,
                            "phone_number": phone_number,
                            "industry_type": industry_type if industry_type else db_record.get("industry_type"),
                            "representative_history": json.dumps(rep_history, ensure_ascii=False),
                            "licensing_history": json.dumps(lic_history, ensure_ascii=False),
                            "update_type": update_type,
                            "prev_business_status": prev_business_status_val,
                            "prev_representative_name": prev_representative_name_val,
                            "prev_business_name": prev_business_name_val,
                            "infer_update_type": infer_update_type,
                            "infer_update_detail": infer_update_detail,
                            "last_event_date": event_date,
                            "last_event_time": event_time,
                            "license_time": license_time,
                            "updated_at": now
                        }
                        business_repo.update_business(lcns_no, updates, conn=conn)
            
            # 모든 처리가 끝난 후 커밋
            conn.commit()
        
        total_elapsed = time.time() - start_time
        logger.info(f"✅ [{service_id} 총 소요시간: {total_elapsed:.2f}초] 모든 변경분({len(new_data_rows)}건)의 DB 업데이트 및 커밋 완료.")
        
        # 신규 데이터가 있으므로 프론트엔드로 SSE 브로드캐스트 발송
        from app.core.events import broadcaster
        update_data = json.dumps({"type": "UPDATE", "message": "신규 업데이트가 발생했다"}, ensure_ascii=False)
        broadcaster.broadcast_sync(update_data)
            
    except Exception as e:
        logger.error(f"❌ {service_id} 크롤러 스케줄 작업 중 치명적인 오류 발생: {e}")

def run_all_scrapers():
    from app.core.config import settings
    services = getattr(settings, "SERVICES", ["I2859", "I2500"])
    for svc in services:
        run_scraper_for_service(svc)

if __name__ == "__main__":
    run_all_scrapers()
