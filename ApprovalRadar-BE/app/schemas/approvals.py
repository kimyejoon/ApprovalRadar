from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class BusinessModel(BaseModel):
    license_no: str
    business_name: Optional[str] = None
    address: Optional[str] = None
    representative_name: Optional[str] = None
    business_status: Optional[str] = None
    license_date: Optional[str] = None
    phone_number: Optional[str] = None
    last_event_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_new: Optional[int] = None
    update_type: Optional[str] = None
    prev_business_status: Optional[str] = None
    prev_representative_name: Optional[str] = None
    prev_business_name: Optional[str] = None
    infer_update_type: Optional[str] = None
    infer_update_detail: Optional[str] = None
    industry_type: Optional[str] = None

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

class DetailListResponse(BaseModel):
    status: str
    data: List[BusinessModel]

class IndicatorStatusDistribution(BaseModel):
    name: str
    value: int

class IndicatorTrendChart(BaseModel):
    date: str
    count: int

class IndicatorsData(BaseModel):
    total_approvals: int
    monthly_approvals: int
    today_approvals: int
    status_distribution: List[IndicatorStatusDistribution]
    trend_chart: List[IndicatorTrendChart]

class IndicatorsResponse(BaseModel):
    status: str
    data: IndicatorsData
