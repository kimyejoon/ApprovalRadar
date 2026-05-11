import datetime
import json
import re
from typing import List
from api_client import FoodSafetyAPIClient
from database import get_db

api_client = FoodSafetyAPIClient()

def parse_representatives(rep_str: str) -> List[str]:
    """
    공동 대표자 파싱 로직
    예: '김**, 이**' -> ['김**', '이**']
    """
    if not rep_str:
        return []
    # 쉼표, '및', '&', '/' 등으로 분리
    parts = re.split(r'[,/&]|및', rep_str)
    return [p.strip() for p in parts if p.strip()]

def fetch_and_update_businesses(date_str: str):
    """
    지정된 날짜(YYYYMMDD) 이후의 인허가 변경 정보를 가져와 DB 업데이트
    """
    start_idx = 1
    chunk_size = 1000
    
    print(f"Starting scraping for date: {date_str}")
    
    while True:
        end_idx = start_idx + chunk_size - 1
        data = api_client.fetch_data("I1200", start_idx, end_idx, CHNG_DT=date_str)
        
        if "row" not in data or not data["row"]:
            break
            
        rows = data["row"]
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            for row in rows:
                lcns_no = row.get("LCNS_NO")
                if not lcns_no:
                    continue
                    
                bssh_nm = row.get("BSSH_NM", "")
                addr = row.get("LOCP_ADDR", "")
                rep_name = row.get("PRSDNT_NM", "")
                business_status = row.get("BSN_STATE_NM", "")
                license_date = row.get("PRMS_DT", "")
                phone_number = row.get("TELNO", "")
                last_updt = row.get("LAST_UPDT_DTM", "")
                cret_dtm = row.get("CRET_DTM", "")
                
                # 우선순위: LAST_UPDT_DTM -> CRET_DTM -> license_date
                event_date = last_updt if last_updt else (cret_dtm if cret_dtm else license_date)
                # 길이 포맷 맞추기 (YYYYMMDD) -> YYYYMMDD 까지만 자르기 (데이터에 따라 길 수 있음)
                if event_date and len(event_date) > 8:
                    event_date = event_date[:8]
                
                cursor.execute("SELECT * FROM businesses WHERE license_no = ?", (lcns_no,))
                db_record = cursor.fetchone()
                
                timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
                now = datetime.datetime.now(timezone_kst).isoformat()
                
                if not db_record:
                    # 신규 등록
                    cursor.execute('''
                        INSERT INTO businesses 
                        (license_no, business_name, address, representative_name, business_status, license_date, phone_number, last_event_date, is_new, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ''', (lcns_no, bssh_nm, addr, rep_name, business_status, license_date, phone_number, event_date, now, now))
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
                        
                    # 영업 상태 감지
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
            
        if len(rows) < chunk_size:
            break
            
        start_idx += chunk_size

def fetch_and_update_change_history(date_str: str):
    """
    I2861 API를 호출하여 명시적인 변경 내역(변경전/변경후)을 가져와 이력을 보강합니다.
    """
    start_idx = 1
    chunk_size = 1000
    
    print(f"Starting change history scraping (I2861) for date: {date_str}")
    
    while True:
        end_idx = start_idx + chunk_size - 1
        data = api_client.fetch_data("I2861", start_idx, end_idx, CHNG_DT=date_str)
        
        if "row" not in data or not data["row"]:
            break
            
        rows = data["row"]
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            for row in rows:
                lcns_no = row.get("LCNS_NO")
                if not lcns_no:
                    continue
                    
                chng_dt = row.get("CHNG_DT", "")
                bf_cn = row.get("CHNG_BF_CN", "").strip()
                af_cn = row.get("CHNG_AF_CN", "").strip()
                reason = row.get("CHNG_PRVNS", "").strip()
                
                # 기존 DB 조회 (업소가 존재할 때만 이력 추가)
                cursor.execute("SELECT * FROM businesses WHERE license_no = ?", (lcns_no,))
                db_record = cursor.fetchone()
                
                if db_record:
                    db_dict = dict(db_record)
                    rep_history = json.loads(db_dict["representative_history"] or "[]")
                    lic_history = json.loads(db_dict["licensing_history"] or "[]")
                    
                    is_updated = False
                    
                    if "대표자" in reason:
                        # 중복 방지 체크
                        is_duplicate = any(h.get("date") == chng_dt and h.get("new") == af_cn for h in rep_history)
                        if not is_duplicate:
                            rep_history.append({
                                "date": chng_dt,
                                "prev": bf_cn,
                                "new": af_cn,
                                "reason": reason
                            })
                            is_updated = True
                    else:
                        # 기타 변경 (상호변경, 소재지변경 등)
                        is_duplicate = any(h.get("date") == chng_dt and h.get("new") == af_cn for h in lic_history)
                        if not is_duplicate:
                            lic_history.append({
                                "date": chng_dt,
                                "type": reason,
                                "prev": bf_cn,
                                "new": af_cn
                            })
                            is_updated = True
                            
                    if is_updated:
                        # 대표자 정보가 API 원문에 포함되어 왔고, 사유가 대표자변경이라면 마스터 테이블도 갱신
                        current_rep = af_cn if "대표자" in reason else db_dict["representative_name"]
                        timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
                        now = datetime.datetime.now(timezone_kst).isoformat()
                        
                        cursor.execute('''
                            UPDATE businesses 
                            SET representative_name = ?,
                                representative_history = ?, licensing_history = ?,
                                last_event_date = ?,
                                updated_at = ?
                            WHERE license_no = ?
                        ''', (
                            current_rep,
                            json.dumps(rep_history, ensure_ascii=False),
                            json.dumps(lic_history, ensure_ascii=False),
                            chng_dt,
                            now, lcns_no
                        ))
            
            conn.commit()
            
        if len(rows) < chunk_size:
            break
            
        start_idx += chunk_size

def run_scraper_job():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(updated_at) FROM businesses")
        last_date_str = cursor.fetchone()[0]
        
    if last_date_str:
        # DB에서 가져온 문자열이 KST timezone offset을 포함할 수 있음
        try:
            dt = datetime.datetime.fromisoformat(last_date_str)
            target_date = dt.strftime("%Y%m%d")
        except ValueError:
            target_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y%m%d")
    else:
        timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
        target_date = (datetime.datetime.now(timezone_kst) - datetime.timedelta(days=3)).strftime("%Y%m%d")
        
    print(f"Scraping Job Triggered. Target Date >= {target_date}")
    fetch_and_update_businesses(target_date)
    fetch_and_update_change_history(target_date)

if __name__ == "__main__":
    run_scraper_job()
