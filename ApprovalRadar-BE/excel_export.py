import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from database import get_db
from typing import Optional

def generate_excel_export(start_date: Optional[str], end_date: Optional[str]) -> io.BytesIO:
    """
    주어진 날짜 조건에 맞춰 데이터를 조회한 후,
    엑셀 파일 데이터(io.BytesIO)로 반환합니다.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        query_conditions = []
        params = []
        
        if start_date:
            query_conditions.append("last_event_date >= ?")
            params.append(start_date)
            
        if end_date:
            query_conditions.append("last_event_date <= ?")
            params.append(end_date)
            
        where_clause = ""
        if query_conditions:
            where_clause = " WHERE " + " AND ".join(query_conditions)
            
        # 데이터 조회 (last_event_date 또는 created_at 기준 내림차순)
        query = f"SELECT * FROM businesses{where_clause} ORDER BY last_event_date DESC, created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()

    # 엑셀 워크북 생성
    wb = Workbook()
    ws = wb.active
    ws.title = "인허가 데이터"

    # 헤더 설정
    headers = ["업소명", "소재지", "인허가번호", "대표자명", "영업상태", "인허가시각", "전화번호"]
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
        ws.append([
            record.get("business_name", ""),
            record.get("address", ""),
            record.get("license_no", ""),
            record.get("representative_name", ""),
            record.get("business_status", ""),
            record.get("license_date", ""),
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
