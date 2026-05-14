import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from database import get_db
from typing import Optional

def generate_excel_export(start_date: Optional[str], end_date: Optional[str], search: Optional[str] = None, regions: Optional[list] = None, infer_update_type: Optional[list] = None, industry_type: Optional[list] = None) -> io.BytesIO:
    """
    주어진 조건에 맞춰 데이터를 조회한 후,
    엑셀 파일 데이터(io.BytesIO)로 반환합니다.
    """
    from app.repositories.business_repository import BusinessRepository
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        repo = BusinessRepository()
        where_clause, params = repo._build_where_clause(search, start_date, end_date, regions, infer_update_type, industry_type)
            
        # 데이터 조회 (last_event_date 또는 created_at 기준 내림차순)
        query = f"SELECT * FROM businesses{where_clause} ORDER BY last_event_date DESC, created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()

    # 엑셀 워크북 생성
    wb = Workbook()
    ws = wb.active
    ws.title = "인허가 데이터"

    # 헤더 설정
    headers = ["업소명", "소재지", "인허가번호", "대표자명", "영업상태", "최초인허가일", "변동인허가일", "전화번호"]
    ws.append(headers)

    # 헤더 스타일 지정
    header_font = Font(bold=True)
    alignment_center = Alignment(horizontal="center", vertical="center")
    
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.alignment = alignment_center

    # 데이터 입력
    for row in rows:
        record = dict(row)
        
        # Format dates if necessary, or just return as is
        last_event_date = record.get("last_event_date", "")
        if last_event_date and len(last_event_date) == 8:
            last_event_date = f"{last_event_date[:4]}-{last_event_date[4:6]}-{last_event_date[6:]}"
            
        license_date = record.get("license_date", "")
        if license_date and len(license_date) == 8:
            license_date = f"{license_date[:4]}-{license_date[4:6]}-{license_date[6:]}"
            
        ws.append([
            record.get("business_name", ""),
            record.get("address", ""),
            record.get("license_no", ""),
            record.get("representative_name", ""),
            record.get("business_status", ""),
            license_date,
            last_event_date,
            record.get("phone_number", "")
        ])

    # 컬럼 너비 자동 조정
    for col in ws.columns:
        max_length = 0
        column_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    val_str = str(cell.value)
                    # 한글 등은 넓게 차지하므로 가중치를 주어 계산 (한글 약 2, 영문/숫자 약 1.2)
                    curr_len = sum(2.1 if ord(c) > 127 else 1.2 for c in val_str)
                    if curr_len > max_length:
                        max_length = curr_len
            except:
                pass
        
        # 최대 길이에 약간의 여백 추가
        ws.column_dimensions[column_letter].width = max_length + 2

    # 메모리에 저장하여 반환
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    return excel_file
