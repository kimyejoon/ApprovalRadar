from pydantic import BaseModel
from typing import List, Optional


class JobStatus(BaseModel):
    job_id: str
    name: str
    next_run: Optional[str] = None
    seconds_remaining: Optional[float] = None
    is_running: bool = False


class SchedulerStatusResponse(BaseModel):
    jobs: List[JobStatus]
    current_time: str


class TriggerResponse(BaseModel):
    success: bool
    message: str


class PageScanEntry(BaseModel):
    page_number: int
    page_start: int
    fingerprint: Optional[str] = None
    last_scanned: Optional[str] = None


class PageScanHistoryResponse(BaseModel):
    total_pages: int
    scanned_pages: int
    entries: List[PageScanEntry]


class TodayDetectionResponse(BaseModel):
    today_date: str
    today_count: int
    yesterday_date: str = ""
    yesterday_count: int = 0
    total_records: int
    scan_coverage_pct: float
    recent_detections: List[dict]


class TailHistoryEntry(BaseModel):
    record_date: str
    total_count: int


class TailHistoryResponse(BaseModel):
    service_id: str
    entries: List[TailHistoryEntry]


class RangeScanRequest(BaseModel):
    start: int   # 스캔 시작 레코드 번호
    end: int     # 스캔 종료 레코드 번호


class ChngDtPollEntry(BaseModel):
    polled_at: str
    total_api_count: int
    new_inserted: int
    already_exists: int
    pages_fetched: int
    elapsed_sec: float


class ChngDtTrendResponse(BaseModel):
    target_date: str
    entries: List[ChngDtPollEntry]
    latest_total: int
    total_inserted: int
    yesterday_date: str
    yesterday_entries: List[ChngDtPollEntry]
    today_date: str
    today_entries: List[ChngDtPollEntry]
