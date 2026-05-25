# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Query, Depends, Path
from typing import List, Optional
import math
from datetime import datetime
import urllib.parse
# pyrefly: ignore [missing-import]
from fastapi.responses import StreamingResponse
from enum import Enum

class SortByEnum(str, Enum):
    created_at = "created_at"
    last_event_date = "last_event_date"
    updated_at = "updated_at"
    license_date = "license_date"
    business_name = "business_name"
    phone = "phone"
    phone_number = "phone_number"
    date = "date"
    representative_name = "representative_name"
    business_status = "business_status"
    license_no = "license_no"
    industry_type = "industry_type"

class SortOrderEnum(str, Enum):
    asc = "asc"
    desc = "desc"

from app.repositories.business_repository import BusinessRepository
from app.core.logger import logger
from excel_export import generate_excel_export
from app.schemas.approvals import (
    BusinessResponse, SingleBusinessResponse, DetailListResponse, PaginationMeta
)

router = APIRouter()

def parse_comma_separated_list(regions: Optional[str] = Query(None, description="콤마(,)로 구분된 지역 목록 (예: 서울,강원,경기)")) -> Optional[List[str]]:
    if not regions:
        return None
    return [r.strip() for r in regions.split(',') if r.strip()]

def parse_industry_type_list(industry_type: Optional[str] = Query(None, description="업종 필터링 (콤마 구분 다중 선택 가능)")) -> Optional[List[str]]:
    if not industry_type:
        return None
    return [r.strip() for r in industry_type.split(',') if r.strip()]

def parse_infer_update_type_list(infer_update_type: Optional[str] = Query(None, description="데이터 필터링 유형 (콤마 구분 다중 선택 가능)")) -> Optional[List[str]]:
    if not infer_update_type:
        return None
    return [r.strip() for r in infer_update_type.split(',') if r.strip()]

def parse_exclude_keywords_list(exclude_keywords: Optional[str] = Query(None, description="콤마(,)로 구분된 상호명 제외 키워드 목록")) -> Optional[List[str]]:
    if not exclude_keywords:
        return None
    return [k.strip() for k in exclude_keywords.split(',') if k.strip()]

def get_business_repo() -> BusinessRepository:
    return BusinessRepository()

@router.get("", response_model=BusinessResponse)
def get_approvals(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=100, description="페이지 당 항목 수"),
    search: Optional[str] = Query(None, description="검색 키워드"),
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYYMMDD)"),
    regions: Optional[List[str]] = Depends(parse_comma_separated_list),
    sort_by: SortByEnum = Query(SortByEnum.created_at, description="정렬 기준 컬럼"),
    sort_order: SortOrderEnum = Query(SortOrderEnum.desc, description="정렬 방향 (asc | desc)"),
    infer_update_type: Optional[List[str]] = Depends(parse_infer_update_type_list),
    industry_type: Optional[List[str]] = Depends(parse_industry_type_list),
    exclude_keywords: Optional[List[str]] = Depends(parse_exclude_keywords_list),
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        result, total_count = repo.get_approvals(page, size, search, start_date, end_date, regions, sort_by.value, sort_order.value, infer_update_type, industry_type, exclude_keywords)
        total_pages = math.ceil(total_count / size) if total_count > 0 else 1
        
        meta = PaginationMeta(
            total_count=total_count,
            current_page=page,
            total_pages=total_pages,
            size=size
        )
            
        return {"status": "success", "data": result, "meta": meta}
    except Exception as e:
        logger.error(f"Database error in get_approvals: {e}")
        raise HTTPException(status_code=500, detail="데이터 제공처의 응답이 지연되고 있거나 내부 오류가 발생했습니다.")

@router.put("/readInfo/{license_no}", summary="인허가 정보 읽음 처리")
def update_read_info(
    license_no: str = Path(..., description="읽음 처리할 인허가번호"),
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        repo.update_read_info(license_no)
        return {"status": "success", "message": "읽음 처리가 완료되었습니다."}
    except Exception as e:
        logger.error(f"Error in update_read_info: {e}")
        raise HTTPException(status_code=500, detail="읽음 처리 중 내부 서버 오류가 발생했습니다.")

@router.get("/export")
def export_approvals_excel(
    search: Optional[str] = Query(None, description="검색 키워드"),
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYYMMDD)"),
    regions: Optional[List[str]] = Depends(parse_comma_separated_list),
    infer_update_type: Optional[List[str]] = Depends(parse_infer_update_type_list),
    industry_type: Optional[List[str]] = Depends(parse_industry_type_list),
    exclude_keywords: Optional[List[str]] = Depends(parse_exclude_keywords_list)
):
    try:
        if not start_date and not end_date:
            today_str = datetime.now().strftime('%Y%m%d')
            start_date_db = today_str
            end_date_db = today_str
        else:
            start_date_db = start_date.replace('-', '') if start_date else None
            end_date_db = end_date.replace('-', '') if end_date else None

        excel_buffer = generate_excel_export(start_date_db, end_date_db, search, regions, infer_update_type, industry_type, exclude_keywords)
        
        date_str = ""
        if start_date_db and end_date_db:
            if start_date_db == end_date_db:
                date_str = f"_{start_date_db}"
            else:
                date_str = f"_{start_date_db}-{end_date_db}"
        elif start_date_db:
            date_str = f"_{start_date_db}"
        elif end_date_db:
            date_str = f"_{end_date_db}"
            
        filename = f"대표자변경분{date_str}.xlsx"
        encoded_filename = urllib.parse.quote(filename)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
        
        return StreamingResponse(
            excel_buffer, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    except Exception as e:
        logger.error(f"Excel export error: {e}")
        raise HTTPException(status_code=500, detail="엑셀 생성 중 서버 오류가 발생했습니다.")

@router.get("/detail", response_model=DetailListResponse)
def get_approval_detail(
    license_no: str = Query(None, description="인허가번호"),
    license_date: str = Query(None, description="최초인허가일 - 레거시"),
    business_name: str = Query(None, description="상호명 - 레거시"),
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        records = []
        if license_no:
            records = repo.get_businesses_by_license_no(license_no)
        elif license_date and business_name:
            records = repo.get_businesses_by_date_and_name(license_date, business_name)

        if not records:
            raise HTTPException(status_code=404, detail="해당 인허가 정보를 찾을 수 없습니다.")
                
        try:
            import json
            for record in records:
                record["representative_history"] = json.loads(record.get("representative_history", "[]"))
                record["licensing_history"] = json.loads(record.get("licensing_history", "[]"))
        except Exception:
            for record in records:
                record["representative_history"] = []
                record["licensing_history"] = []
            
        return {"status": "success", "data": records}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error in get_approval_detail: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다.")


@router.post("/{license_no}/sync-history")
async def sync_business_history(
    license_no: str = Path(..., description="인허가번호"),
    repo: BusinessRepository = Depends(get_business_repo)
):
    """
    특정 업소의 I2861 전체 변경이력을 즉시 조회하고 DB에 저장합니다.
    - DB에 없는 이력은 INSERT
    - 완료 후 해당 업소의 전체 DB 이력을 반환
    """
    import json as _json
    import asyncio
    from app.clients.foodsafety_api import ApiClient
    from app.services.scraper.mapper import map_row_fields, parse_datetime_fields
    from app.services.scraper.persistence_batch import persist_batch_crawl

    client = ApiClient()
    try:
        res = await client.fetch_data("I2861", 1, 1000, LCNS_NO=license_no, SYS_SYNC="LIVE")
    except Exception as e:
        logger.error(f"[세부조회] I2861 API 오류 (LCNS_NO={license_no}): {e}")
        raise HTTPException(status_code=502, detail=f"식품나라 API 조회 실패: {e}")
    finally:
        await client.aclose()

    api_rows = []
    if res and "I2861" in res:
        block = res["I2861"]
        if isinstance(block, dict) and block.get("RESULT", {}).get("CODE") == "INFO-000":
            api_rows = block.get("row", [])

    new_count = 0
    if api_rows:
        mapped_rows = []
        for row in api_rows:
            fields = map_row_fields("I2861", row)
            if not fields:
                continue
            event_date, event_time, license_date_parsed, license_time = parse_datetime_fields(
                fields.get("event_date_raw", ""), fields.get("license_date", "")
            )
            if not event_date:
                continue
            mapped_rows.append({
                "fields": fields,
                "event_date": event_date,
                "event_time": event_time,
                "license_date": license_date_parsed or "",
                "license_time": license_time or "",
                "raw_row": row,
            })

        if mapped_rows:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: persist_batch_crawl("I2861", mapped_rows, "manual_sync")
            )
            new_count = result.get("new_indexed", 0)
            logger.info(
                f"[세부조회] LCNS_NO={license_no} 동기화 완료: "
                f"API {len(api_rows)}건 조회, 신규 {new_count}건 저장"
            )

    records = repo.get_businesses_by_license_no(license_no)
    for record in records:
        try:
            record["representative_history"] = _json.loads(record.get("representative_history", "[]"))
            record["licensing_history"] = _json.loads(record.get("licensing_history", "[]"))
        except Exception:
            record["representative_history"] = []
            record["licensing_history"] = []

    return {"status": "success", "data": records, "synced": new_count, "api_total": len(api_rows)}

