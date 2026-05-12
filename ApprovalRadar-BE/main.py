from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import math
from database import init_db
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import run_scraper_job
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import urllib.parse
from fastapi.responses import StreamingResponse
from excel_export import generate_excel_export

# Repositories
from app.repositories.business_repository import BusinessRepository
from app.core.logger import logger

# 프론트엔드 개발자가 Swagger에서 확인할 수 있는 응답 데이터 형태(Schema)를 정의합니다.
class BusinessModel(BaseModel):
    license_no: str
    business_name: Optional[str] = None
    address: Optional[str] = None
    representative_name: Optional[str] = None
    business_status: Optional[str] = None
    license_date: Optional[str] = None
    phone_number: Optional[str] = None
    representative_history: List[Dict[str, Any]] = []
    licensing_history: List[Dict[str, Any]] = []
    last_event_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_new: Optional[int] = None

class PaginationMeta(BaseModel):
    total_count: int
    current_page: int
    total_pages: int
    size: int

class BusinessResponse(BaseModel):
    status: str
    data: List[BusinessModel]
    meta: Optional[PaginationMeta] = None

class SingleBusinessResponse(BaseModel):
    status: str
    data: BusinessModel

class IndicatorStatusDistribution(BaseModel):
    name: str
    value: int

class IndicatorTrendChart(BaseModel):
    date: str
    count: int

class IndicatorsData(BaseModel):
    total_approvals: int
    status_distribution: List[IndicatorStatusDistribution]
    trend_chart: List[IndicatorTrendChart]

class IndicatorsResponse(BaseModel):
    status: str
    data: IndicatorsData

def parse_comma_separated_list(regions: Optional[str] = Query(None, description="콤마(,)로 구분된 지역 목록 (예: 서울,강원,경기)")) -> Optional[List[str]]:
    if not regions:
        return None
    return [r.strip() for r in regions.split(',') if r.strip()]

def get_business_repo() -> BusinessRepository:
    return BusinessRepository()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Initializing Database...")
    init_db()
    
    logger.info("Starting APScheduler for 10-minute scraping intervals...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scraper_job, 'interval', minutes=10)
    scheduler.start()
    
    # Run once on startup to catch up
    run_scraper_job()
    
    yield
    
    # Shutdown logic
    logger.info("Shutting down...")
    scheduler.shutdown()

app = FastAPI(title="Food Safety Data API", lifespan=lifespan)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Food Safety Data API"}

@app.get("/api/v1/approvals", response_model=BusinessResponse)
def get_approvals(
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(10, ge=1, le=100, description="페이지 당 항목 수"),
    search: Optional[str] = Query(None, description="검색 키워드 (상호명, 인허가번호 등)"),
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYY-MM-DD)"),
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

@app.get("/api/v1/approvals/indicators", response_model=IndicatorsResponse)
def get_approval_indicators(
    search: Optional[str] = Query(None, description="검색 키워드 (상호명, 인허가번호 등)"),
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYY-MM-DD)"),
    regions: Optional[List[str]] = Depends(parse_comma_separated_list),
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        total_approvals, status_distribution, trend_chart = repo.get_indicators(search, start_date, end_date, regions)
            
        return {
            "status": "success",
            "data": {
                "total_approvals": total_approvals,
                "status_distribution": status_distribution,
                "trend_chart": trend_chart
            }
        }
    except Exception as e:
        logger.error(f"Database error in get_approval_indicators: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

@app.get("/api/v1/approvals/export")
def export_approvals_excel(
    start_date: Optional[str] = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="조회 종료일 (YYYY-MM-DD)")
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

@app.get("/api/v1/approvals/{approval_id}", response_model=SingleBusinessResponse)
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
