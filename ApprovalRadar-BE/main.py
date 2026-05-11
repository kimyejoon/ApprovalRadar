from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import json
import math
from database import init_db, get_db
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import run_scraper_job
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

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

def parse_comma_separated_list(regions: Optional[str] = Query(None, description="콤마(,)로 구분된 지역 목록 (예: 서울,강원,경기)")) -> Optional[List[str]]:
    if not regions:
        return None
    return [r.strip() for r in regions.split(',') if r.strip()]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("Initializing Database...")
    init_db()
    
    print("Starting APScheduler for 10-minute scraping intervals...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scraper_job, 'interval', minutes=10)
    scheduler.start()
    
    # Run once on startup to catch up
    run_scraper_job()
    
    yield
    
    # Shutdown logic
    print("Shutting down...")
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
    sort_order: str = Query("desc", description="정렬 방향 (asc | desc)")
):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            query_conditions = []
            params = []
            
            if search:
                query_conditions.append("(business_name LIKE ? OR license_no LIKE ?)")
                search_term = f"%{search}%"
                params.extend([search_term, search_term])
                
            if start_date:
                query_conditions.append("last_event_date >= ?")
                params.append(start_date)
                
            if end_date:
                query_conditions.append("last_event_date <= ?")
                params.append(end_date)
                
            if regions:
                region_conditions = []
                for r in regions:
                    region_conditions.append("address LIKE ?")
                    params.append(f"%{r}%")
                if region_conditions:
                    query_conditions.append(f"({' OR '.join(region_conditions)})")
            
            where_clause = ""
            if query_conditions:
                where_clause = " WHERE " + " AND ".join(query_conditions)
            
            # 전체 데이터 개수 구하기
            count_query = f"SELECT COUNT(*) FROM businesses{where_clause}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # 정렬 설정
            valid_sort_columns = ["created_at", "last_event_date", "updated_at", "license_date", "business_name"]
            if sort_by not in valid_sort_columns:
                sort_by = "created_at"
            order = "ASC" if sort_order.lower() == "asc" else "DESC"
            
            # 오프셋 계산 및 데이터 조회
            offset = (page - 1) * size
            
            data_query = f"SELECT * FROM businesses{where_clause} ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
            data_params = params + [size, offset]
            
            cursor.execute(data_query, data_params)
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                record = dict(row)
                # Parse JSON strings back to lists
                try:
                    record["representative_history"] = json.loads(record.get("representative_history", "[]"))
                    record["licensing_history"] = json.loads(record.get("licensing_history", "[]"))
                except Exception:
                    record["representative_history"] = []
                    record["licensing_history"] = []
                result.append(record)
                
            # 전체 페이지 수 계산
            total_pages = math.ceil(total_count / size) if total_count > 0 else 1
            
            meta = PaginationMeta(
                total_count=total_count,
                current_page=page,
                total_pages=total_pages,
                size=size
            )
                
        return {"status": "success", "data": result, "meta": meta}
    except Exception as e:
        # DB Error handling, returns a user-friendly message as required
        print(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="데이터 제공처의 응답이 지연되고 있거나 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

@app.get("/api/v1/approvals/{approval_id}", response_model=SingleBusinessResponse)
def get_approval_detail(approval_id: str):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM businesses WHERE license_no = ?", (approval_id,))
            row = cursor.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="해당 인허가 정보를 찾을 수 없습니다.")
                
            record = dict(row)
            try:
                record["representative_history"] = json.loads(record.get("representative_history", "[]"))
                record["licensing_history"] = json.loads(record.get("licensing_history", "[]"))
            except Exception:
                record["representative_history"] = []
                record["licensing_history"] = []
                
        return {"status": "success", "data": record}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
