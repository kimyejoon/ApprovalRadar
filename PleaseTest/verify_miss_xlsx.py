import os
import sys
import asyncio
import sqlite3
import pandas as pd
from datetime import datetime

# 백엔드 모듈 경로 추가
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

# UTF-8 출력 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.worker_pool import ApiWorkerPool
from app.clients.foodsafety_api import ApiClient
from app.core.config import settings

xlsx_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\업소인허가 데이터 조회(2026-05-22) (3).xlsx"
db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

async def check_missing_records():
    print("[1] 엑셀 파일 로드 중...")
    if not os.path.exists(xlsx_path):
        print(f"❌ 엑셀 파일이 없습니다: {xlsx_path}")
        return

    # 인허가번호 컬럼 추출
    df = pd.read_excel(xlsx_path)
    print(f"엑셀 전체 행 수: {len(df)}행")
    
    # 엑셀 허가일자 포맷 정리
    df['허가일자_str'] = df['허가일자'].dropna().astype(int).astype(str)
    
    # 인허가번호가 정수형으로 읽혀 .0 이 붙는 경우 소수점 제거 처리
    df['인허가번호_str'] = df['인허가번호'].dropna().astype(int).astype(str)
    
    lcns_list = df['인허가번호_str'].unique().tolist()
    print(f"-> 엑셀에서 고유 인허가번호 {len(lcns_list)}건 로드 완료.")

    # 5월 22일 이후 허가된 신규 업소 확인
    xlsx_new_regs = df[df['허가일자_str'] >= "20260522"]
    print(f"-> 엑셀 내 2026-05-22 이후 신규 허가(등록) 업소: {len(xlsx_new_regs)}건")
    for idx, r in xlsx_new_regs.iterrows():
        print(f"   * 신규허가업소: {r['업소명']} | {r['인허가번호_str']} | 허가일: {r['허가일자_str']} | 업종: {r['업종']}")

    print("\n[2] 로컬 DB에서 이미 수집된 인허가 정보 로드 중...")
    if not os.path.exists(db_path):
        print(f"❌ DB 파일이 존재하지 않습니다: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # DB에 저장된 (license_no, last_event_date) 목록 및 license_no 자체의 목록 수집
    db_records = set()
    db_all_licenses = set()
    rows = cursor.execute("SELECT license_no, last_event_date FROM businesses").fetchall()
    for r in rows:
        lcns = r['license_no']
        evt_dt = r['last_event_date']
        if lcns:
            db_all_licenses.add(lcns.strip())
            if evt_dt:
                db_records.add((lcns.strip(), evt_dt.strip()))
            
    print(f"-> DB에서 (license_no, last_event_date) 쌍 {len(db_records)}건 로드 완료.")
    print(f"-> DB에서 고유 license_no 개수: {len(db_all_licenses)}건")

    # API 키 회전 및 멀티워커 풀 구성 (5개 워커)
    print("\n[3] ApiWorkerPool 초기화 중...")
    pool = ApiWorkerPool(n_workers=5, label="XLSX-DoubleCheck")
    semaphore = pool.semaphore
    
    api_results = []
    total_to_check = len(lcns_list)
    done_count = 0
    lock = asyncio.Lock()

    async def fetch_one(lcns: str, worker_idx: int):
        nonlocal done_count
        async with semaphore:
            client = pool.get_client(worker_idx)
            try:
                res = await client.fetch_data("I2861", 1, 20, LCNS_NO=lcns)
                rows = []
                if res and "I2861" in res:
                    rows = res["I2861"].get("row", [])
                
                async with lock:
                    done_count += 1
                    if done_count % 20 == 0 or done_count == total_to_check:
                        print(f"   -> API 조회 진행률: [{done_count}/{total_to_check}] ({(done_count/total_to_check)*100:.1f}%)")
                    
                    if rows:
                        for row in rows:
                            api_results.append({
                                "LCNS_NO": row.get("LCNS_NO", "").strip(),
                                "BSSH_NM": row.get("BSSH_NM", "").strip(),
                                "CHNG_DT": row.get("CHNG_DT", "").strip(),
                                "CHNG_PRVNS": row.get("CHNG_PRVNS", "").strip(),
                                "INDUTY_CD_NM": row.get("INDUTY_CD_NM", "").strip(),
                                "SITE_ADDR": row.get("SITE_ADDR", "").strip(),
                                "CHNG_BF_CN": row.get("CHNG_BF_CN", "").strip(),
                                "CHNG_AF_CN": row.get("CHNG_AF_CN", "").strip()
                            })
            except Exception as e:
                async with lock:
                    done_count += 1
                    print(f"❌ LCNS_NO {lcns} 조회 중 에러 발생: {e}")

    # 비동기 조회를 동시에 실행
    print(f"\n[4] I2861 개별 API 조회 시작 (대상: {total_to_check}건)...")
    tasks = [fetch_one(lcns, idx) for idx, lcns in enumerate(lcns_list)]
    await asyncio.gather(*tasks)
    
    print(f"\n-> API 개별 조회 완료. 총 {len(api_results)}개 변경 이벤트 반환됨.")

    # API 응답 변경일자 분포 확인
    chng_dates = [r["CHNG_DT"] for r in api_results if r.get("CHNG_DT")]
    chng_df = pd.Series(chng_dates)
    print("\n[검증 추가] API 응답 변경일자(CHNG_DT) 최신순 분포:")
    print(chng_df.value_counts().sort_index(ascending=False).head(15))

    # 1. 5월 22일 이후의 변경일자 건 필터링 및 DB 누락 검사
    cutoff_date = "20260522"
    print(f"\n[5] 검증 A: 실제 인허가변경일(CHNG_DT)이 {cutoff_date} 이후인 데이터 누락 검사")
    
    recent_events = [e for e in api_results if e["CHNG_DT"] >= cutoff_date]
    print(f"-> API 변경 이벤트 중 {cutoff_date} 이후 건수: {len(recent_events)}건")

    missing_events = []
    for ev in recent_events:
        lcns = ev["LCNS_NO"]
        chng_dt = ev["CHNG_DT"]
        if (lcns, chng_dt) not in db_records:
            missing_events.append(ev)

    # 2. 엑셀의 모든 인허가번호가 DB에 아예 존재하지 않는 경우가 있는지 검증 (신규 누락 포함)
    print("\n[6] 검증 B: 엑셀의 인허가번호 135건 중 로컬 DB에 아예 존재하지 않는 업소 검사")
    missing_licenses_in_db = []
    for idx, r in df.iterrows():
        lcns = r['인허가번호_str']
        if lcns not in db_all_licenses:
            missing_licenses_in_db.append({
                "인허가번호": lcns,
                "업소명": r["업소명"],
                "허가일자": r["허가일자_str"],
                "업종": r["업종"],
                "주소": r["주소"]
            })

    print(f"-> DB에 아예 존재하지 않는 엑셀 업소 수: {len(missing_licenses_in_db)}건")
    for m_lcns in missing_licenses_in_db:
        print(f"   * DB 누락의심 업소: {m_lcns['업소명']} ({m_lcns['인허가번호']}) | 허가일: {m_lcns['허가일자']} | 업종: {m_lcns['업종']}")

    print("\n==================== 최종 검증 결과 요약 ====================")
    print(f"1. API 분석 대상 고유 업소 수: {total_to_check}건")
    print(f"2. {cutoff_date} 이후의 실제 API 변경일(CHNG_DT)을 갖는 이벤트 누락 수: {len(missing_events)}건")
    print(f"3. 로컬 DB에 아예 수집되지 않고 누락된 엑셀 업소 수: {len(missing_licenses_in_db)}건")
    
    if len(missing_events) > 0 or len(missing_licenses_in_db) > 0:
        print("\n⚠️ [경고] 미탐지/누락 건이 발견되었습니다. 정밀 조사가 필요합니다.")
    else:
        print("\n✅ [검증 완료] 누락이나 미탐지 건이 전혀 발견되지 않았습니다. 동기화가 완벽합니다!")
    print("===========================================================")

    conn.close()

if __name__ == "__main__":
    asyncio.run(check_missing_records())
