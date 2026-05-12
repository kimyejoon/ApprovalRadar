from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
import math
import time
from datetime import datetime
import urllib.parse
from fastapi.responses import StreamingResponse

from app.repositories.business_repository import BusinessRepository
from app.core.logger import logger
from excel_export import generate_excel_export
from app.schemas.approvals import (
    BusinessResponse, IndicatorsResponse, SingleBusinessResponse, PaginationMeta
)

router = APIRouter()

INDICATORS_CACHE = {}
CACHE_TTL = 600  # 10 minutes

def parse_comma_separated_list(regions: Optional[str] = Query(None, description="콤마(,)로 구분된 지역 목록 (예: 서울,강원,경기)")) -> Optional[List[str]]:
    if not regions:
        return None
    return [r.strip() for r in regions.split(',') if r.strip()]

def get_business_repo() -> BusinessRepository:
    return BusinessRepository()

@router.get("", response_model=BusinessResponse)
def get_approvals(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=100, description="페이지 당 항목 수"),
    search: Optional[str] = Query(None, description="검색 키워드 (상호명, 인허가번호 등)"),
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYYMMDD)"),
    regions: Optional[List[str]] = Depends(parse_comma_separated_list),
    sort_by: str = Query("created_at", description="정렬 기준 컬럼"),
    sort_order: str = Query("desc", description="정렬 방향 (asc | desc)"),
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        result, total_count = repo.get_approvals(page, size, search, start_date, end_date, regions, sort_by, sort_order)
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
        raise HTTPException(status_code=500, detail="데이터 제공처의 응답이 지연되고 있거나 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

@router.get("/indicators", response_model=IndicatorsResponse)
def get_approval_indicators(
    search: Optional[str] = Query(None, description="검색 키워드 (상호명, 인허가번호 등)"),
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYYMMDD)"),
    regions: Optional[List[str]] = Depends(parse_comma_separated_list),
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        cache_key = str((search, start_date, end_date, tuple(regions) if regions else None))
        cached = INDICATORS_CACHE.get(cache_key)
        
        if cached and time.time() - cached['time'] < CACHE_TTL:
            return cached['data']
            
        total_approvals, status_distribution, trend_chart = repo.get_indicators(search, start_date, end_date, regions)
            
        response_data = {
            "status": "success",
            "data": {
                "total_approvals": total_approvals,
                "status_distribution": status_distribution,
                "trend_chart": trend_chart
            }
        }
        
        INDICATORS_CACHE[cache_key] = {"time": time.time(), "data": response_data}
        return response_data
    except Exception as e:
        logger.error(f"Database error in get_approval_indicators: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

@router.get("/export")
def export_approvals_excel(
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYYMMDD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYYMMDD)")
):
    try:
        # Default to today if both are empty
        if not start_date and not end_date:
            today_str = datetime.now().strftime('%Y%m%d')
            start_date_db = today_str
            end_date_db = today_str
        else:
            start_date_db = start_date.replace('-', '') if start_date else None
            end_date_db = end_date.replace('-', '') if end_date else None

        # Generate the excel file in a buffer
        excel_buffer = generate_excel_export(start_date_db, end_date_db)
        
        # Build filename
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

        # URL encode filename for Content-Disposition header
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

@router.get("/{approval_id}", response_model=SingleBusinessResponse)
def get_approval_detail(approval_id: str, repo: BusinessRepository = Depends(get_business_repo)):
    try:
        record = repo.get_business_by_license_no(approval_id)
        if not record:
            raise HTTPException(status_code=404, detail="해당 인허가 정보를 찾을 수 없습니다.")
                
        try:
            import json
            record["representative_history"] = json.loads(record.get("representative_history", "[]"))
            record["licensing_history"] = json.loads(record.get("licensing_history", "[]"))
        except Exception:
            record["representative_history"] = []
            record["licensing_history"] = []
            
        return {"status": "success", "data": record}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error in get_approval_detail: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
