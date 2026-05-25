import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from database import get_db
from typing import Optional
from app.repositories.query_builder import build_business_where_clause

def generate_excel_export(start_date: Optional[str], end_date: Optional[str], search: Optional[str] = None, regions: Optional[list] = None, infer_update_type: Optional[list] = None, industry_type: Optional[list] = None, exclude_keywords: Optional[list] = None) -> io.BytesIO:
    """
    주어진 조건에 맞춰 데이터를 조회한 후,
    엑셀 파일 데이터(io.BytesIO)로 반환합니다.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # repositories.query_builder 함수를 사용하여 WHERE 절 생성
        where_clause, params = build_business_where_clause(search, start_date, end_date, regions, infer_update_type, industry_type, exclude_keywords)
            
        # 데이터 조회 (last_event_date 또는 created_at 기준 내림차순)
        query = f"SELECT * FROM businesses{where_clause} ORDER BY last_event_date DESC, created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()

    # 엑셀 워크북 생성
    wb = Workbook()
    ws = wb.active
    ws.title = "인허가 데이터"

    # 변경타입 한글 매핑 (프론트엔드 CATEGORY_NAMES와 동일)
    CATEGORY_NAMES = {
        '신규등록': '신규등록',
        '상태변경': '상태 변경',
        '대표자변경': '대표 변경',
        '변경민원-상호명': '상호 변경',
        '변경민원-주소': '주소 변경',
        '변경민원-성함': '성함 변경',
        '초기수집(과거변경있음)': '기타',
    }

    # 헤더 설정 (프론트엔드 테이블 컬럼 순서 및 한글명과 완전 일치)
    headers = ["업소명", "인허가번호", "소재지", "대표자명", "업종", "변경 타입", "인허가 변동시각", "전화번호"]
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

        # 업소명 (이전 상호명)
        business_name = record.get("business_name", "") or ""
        prev_name = record.get("prev_business_name", "") or ""
        if prev_name:
            business_name = f"{business_name} (이전: {prev_name})"

        # 대표자명 (이전 대표자명)
        rep_name = record.get("representative_name", "") or ""
        prev_rep = record.get("prev_representative_name", "") or ""
        if prev_rep:
            rep_name = f"{rep_name} (이전: {prev_rep})"

        # 변경타입: infer_update_type → 한글 매핑 및 상세내역 포함
        raw_update_type = record.get("infer_update_type", "") or ""
        change_type = CATEGORY_NAMES.get(raw_update_type, raw_update_type)
        update_detail = record.get("infer_update_detail", "") or ""
        if update_detail:
            change_type = f"{change_type} ({update_detail})"

        # 인허가변동시각: last_event_time (ISO 8601 → 한국 가독성 포맷)
        last_event_time = record.get("last_event_time", "") or ""
        if last_event_time:
            try:
                from datetime import datetime as _dt
                last_event_time = _dt.fromisoformat(last_event_time).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass  # 파싱 실패 시 원본 유지

        ws.append([
            business_name,
            record.get("license_no", ""),
            record.get("address", ""),
            rep_name,
            record.get("industry_type", "") or "",
            change_type,
            last_event_time,
            record.get("phone_number", "") or "",
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
