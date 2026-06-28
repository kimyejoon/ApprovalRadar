import os
import sys
import sqlite3
from openpyxl import load_workbook
import asyncio

# BE path
sys.path.append(r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.clients.foodsafety_api import ApiClient

xlsx_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\PleaseTest\업소인허가 데이터 조회(2026-06-19).xlsx"
db_path = r"c:\Users\YEJOON\Desktop\DevProject\ApprovalRadar\ApprovalRadar-BE\food_safety.db"

async def main():
    print("[1] 엑셀 파일에서 '처갓집' 및 '지코바' 검색...")
    excel_found = []
    if os.path.exists(xlsx_path):
        wb = load_workbook(xlsx_path, read_only=True)
        sheet = wb.active
        
        # Get headers
        headers = []
        for r_idx, row_vals in enumerate(sheet.iter_rows(values_only=True), 1):
            if r_idx == 1:
                headers = list(row_vals)
                continue
            
            # Map row to dict
            row_dict = dict(zip(headers, row_vals))
            bssh_nm = str(row_dict.get('업소명') or '')
            lcns_no = row_dict.get('인허가번호')
            if lcns_no is not None:
                try:
                    lcns_no = str(int(float(lcns_no)))
                except Exception:
                    lcns_no = str(lcns_no)
            else:
                lcns_no = ''
                
            addr = str(row_dict.get('주소') or '')
            prms_dt = str(row_dict.get('허가일자') or '')
            induty = str(row_dict.get('업종') or '')
            
            if any(term in bssh_nm or term in addr for term in ['처갓집', '지코바', '퇴계', '면목']):
                print(f"  - Excel: {bssh_nm} ({lcns_no}) | 허가일자: {prms_dt} | 업종: {induty} | 주소: {addr}")
                excel_found.append({
                    "license_no": lcns_no,
                    "name": bssh_nm
                })
        wb.close()
        print(f"엑셀 내 일치 항목 수: {len(excel_found)}건")
    else:
        print("엑셀 파일 없음.")

    print("\n[2] 로컬 DB에서 '처갓집' 및 '지코바' 검색...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    db_matches = cursor.execute(
        "SELECT id, license_no, business_name, last_event_date, infer_update_type, change_before, change_after FROM businesses WHERE business_name LIKE '%처갓집%' OR business_name LIKE '%지코바%' OR business_name LIKE '%퇴계%' OR business_name LIKE '%면목%'"
    ).fetchall()
    
    print(f"DB 내 일치 항목 수: {len(db_matches)}건")
    for r in db_matches[:20]:
        print(f"  - DB: {r['business_name']} ({r['license_no']}) | last_event_date: {r['last_event_date']} | type: {r['infer_update_type']}")
        
    # Also check if the specific license numbers from Excel are in DB
    print("\n[3] 엑셀에서 찾은 특정 인허가번호의 DB 내역 조회...")
    for item in excel_found:
        lcns = item['license_no']
        if not lcns:
            continue
        rows = cursor.execute(
            "SELECT id, license_no, business_name, last_event_date, infer_update_type, change_before, change_after, collected_by FROM businesses WHERE license_no = ?",
            (lcns,)
        ).fetchall()
        print(f"  * LCNS {lcns} ({item['name']}) -> DB 내 레코드 수: {len(rows)}")
        for r in rows:
            print(f"    - ID: {r['id']} | Date: {r['last_event_date']} | Type: {r['infer_update_type']} | Before: {repr(r['change_before'])} | After: {repr(r['change_after'])} | Collected By: {r['collected_by']}")

    # Check OpenAPI
    print("\n[4] OpenAPI에서 실시간 데이터 및 변경이력 조회 (I2861/I2500)...")
    async with ApiClient() as client:
        for item in excel_found:
            lcns = item['license_no']
            if not lcns:
                continue
            print(f"\n>>> LICENSE: {lcns} ({item['name']})")
            
            # Query I2861 (변경 이력)
            res_i2861 = await client.fetch_data("I2861", 1, 20, LCNS_NO=lcns)
            rows_i2861 = res_i2861.get("I2861", {}).get("row", []) if res_i2861 else []
            print(f"  * OpenAPI I2861 (변경이력) 결과 수: {len(rows_i2861)}")
            for row in rows_i2861:
                print(f"    - Date: {row.get('CHNG_DT')} | Reason: {row.get('CHNG_PRVNS')} | Before: {repr(row.get('CHNG_BF_CN'))} | After: {repr(row.get('CHNG_AF_CN'))}")

            # Query I2500 (업소기본정보)
            res_i2500 = await client.fetch_data("I2500", 1, 10, LCNS_NO=lcns)
            rows_i2500 = res_i2500.get("I2500", {}).get("row", []) if res_i2500 else []
            print(f"  * OpenAPI I2500 (기본정보) 결과 수: {len(rows_i2500)}")
            for row in rows_i2500:
                print(f"    - BSSH_NM: {row.get('BSSH_NM')} | ADDR: {row.get('ADDR')} | PRMS_DT: {row.get('PRMS_DT')} | INDUTY: {row.get('INDUTY_CD_NM')}")

    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
