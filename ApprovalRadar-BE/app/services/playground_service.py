from app.services.playground.scheduler import get_scheduler_status_data, trigger_job_task, JOB_NAMES
from app.services.playground.scanner import trigger_range_scan_task, get_page_scan_history_data, get_tail_history_data
from app.services.playground.stats import get_today_detection_data, get_chng_dt_trend_data

def get_playground_summary_data(service_id: str = "I2861") -> dict:
    """플레이그라운드 대시보드 조회를 위한 통합 데이터를 반환합니다."""
    return {
        "scheduler": get_scheduler_status_data(),
        "today": get_today_detection_data(service_id),
        "tail_history": get_tail_history_data(service_id),
        "page_scan": get_page_scan_history_data(service_id),
    }
