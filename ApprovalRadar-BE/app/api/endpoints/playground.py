"""
Playground API 엔드포인트 — 크롤러 개발 테스트 및 모니터링용.
라우팅 및 응답 매핑 레이어.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from app.api.schemas.playground import (
    SchedulerStatusResponse,
    TriggerResponse,
    RangeScanRequest,
    PageScanHistoryResponse,
    TodayDetectionResponse,
    TailHistoryResponse,
    ChngDtTrendResponse,
    PlaygroundSummaryResponse
)
from app.services import playground_service

router = APIRouter()


@router.get("/summary", response_model=PlaygroundSummaryResponse)
async def get_playground_summary(service_id: str = "I2861"):
    """스케줄러 상태, 오늘 감지 이력, tail 히스토리, 페이지 스캔 상태를 포함한 통합 요약 정보를 조회합니다."""
    return playground_service.get_playground_summary_data(service_id)


@router.get("/scheduler-status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    """현재 APScheduler 잡 목록과 다음 실행 시간을 반환합니다."""
    return playground_service.get_scheduler_status_data()


@router.post("/trigger/range-scan", response_model=TriggerResponse)
async def trigger_range_scan(req: RangeScanRequest):
    """지정 범위를 즉시 스캔합니다. start~end 구간의 페이지를 순차 스캔."""
    try:
        if req.start < 1 or req.end < req.start:
            return TriggerResponse(success=False, message=f"잘못된 범위: {req.start}~{req.end}")

        playground_service.trigger_range_scan_task(req.start, req.end)
        pages = (req.end - req.start + 1000) // 1000
        return TriggerResponse(
            success=True,
            message=f"🎯 Range Scan 등록: {req.start:,}~{req.end:,} ({pages}p)"
        )
    except Exception as e:
        return TriggerResponse(success=False, message=str(e))


@router.post("/trigger/{job_type}", response_model=TriggerResponse)
async def trigger_job(job_type: str):
    """지정한 잡을 즉시 실행합니다.
    job_type: scraper | oldest_first_scan | rolling_scan | tail_ping | chng_dt_poll | smart_sweep_micro | smart_sweep_full
    """
    try:
        msg = playground_service.trigger_job_task(job_type)
        return TriggerResponse(success=True, message=msg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return TriggerResponse(success=False, message=str(e))


@router.get("/page-scan-history/{service_id}", response_model=PageScanHistoryResponse)
async def get_page_scan_history(service_id: str = "I2861"):
    """page_fingerprints + page_scan_times를 페이지별 테이블로 변환하여 반환합니다."""
    return playground_service.get_page_scan_history_data(service_id)


@router.get("/today-detection/{service_id}", response_model=TodayDetectionResponse)
async def get_today_detection(service_id: str = "I2861"):
    """오늘 + 어제 CHNG_DT로 감지된 레코드 현황을 반환합니다."""
    return playground_service.get_today_detection_data(service_id)


@router.get("/tail-history/{service_id}", response_model=TailHistoryResponse)
async def get_tail_history(service_id: str = "I2861"):
    """최근 90일 known_tail 변화 추이를 반환합니다."""
    return playground_service.get_tail_history_data(service_id)


@router.get("/chng-dt-trend")
async def get_chng_dt_trend():
    """
    CHNG_DT Poller 시간별 트렌드 데이터.
    어제+오늘 날짜의 폴링 이력을 반환합니다.
    """
    return playground_service.get_chng_dt_trend_data()
