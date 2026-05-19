"""
Playground API 엔드포인트 — 크롤러 개발 테스트 및 모니터링용.

스케줄러 상태, 수동 트리거, 페이지 스캔 히스토리, 오늘 감지 현황,
known_tail 일별 추이를 제공합니다.
"""
import asyncio
import json
from datetime import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
from typing import List, Optional

from app.core.logger import logger
from database import get_db

router = APIRouter()


# ─── 응답 스키마 ─────────────────────────────────────────────────────────────

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


# ─── 스케줄러 상태 조회 ──────────────────────────────────────────────────────

JOB_NAMES = {
    "scraper_job": "🔍 Scraper (30분 주기)",
    "tail_ping_job": "📡 Tail Ping (5분 주기)",
    "key_recovery_job": "🔑 키 회복 체크 (10분)",
    "backfill_job": "📋 업종 백필 (6시간)",
    "vacuum_job": "🗑️ DB 최적화 (일요일 3시)",
    "backup_job": "💾 DB 백업 (매일 4시)",
    "daily_bootstrap_job": "🌅 Daily Bootstrap (매일 9시)",
    "evening_dense_start_job": "🌆 저녁 고밀도 시작 (18:30)",
    "evening_dense_end_job": "🌙 저녁 고밀도 종료 (20:30)",
}


@router.get("/scheduler-status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    """현재 APScheduler 잡 목록과 다음 실행 시간을 반환합니다."""
    from app.core.scheduler import scheduler

    now = datetime.now()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        remaining = None
        if next_run:
            remaining = (next_run.replace(tzinfo=None) - now).total_seconds()

        jobs.append(JobStatus(
            job_id=job.id,
            name=JOB_NAMES.get(job.id, job.id),
            next_run=next_run.strftime("%H:%M:%S") if next_run else None,
            seconds_remaining=round(remaining, 1) if remaining else None,
            is_running=False,
        ))

    # 남은 시간 기준 정렬
    jobs.sort(key=lambda j: j.seconds_remaining if j.seconds_remaining is not None else 99999)

    return SchedulerStatusResponse(
        jobs=jobs,
        current_time=now.strftime("%Y-%m-%d %H:%M:%S"),
    )


# ─── 수동 트리거 ─────────────────────────────────────────────────────────────

class RangeScanRequest(BaseModel):
    start: int   # 스캔 시작 레코드 번호 (예: 1, 500001)
    end: int     # 스캔 종료 레코드 번호 (예: 10000, 952999)


@router.post("/trigger/range-scan", response_model=TriggerResponse)
async def trigger_range_scan(req: RangeScanRequest):
    """지정 범위를 즉시 스캔합니다. start~end 구간의 페이지를 순차 스캔."""
    try:
        if req.start < 1 or req.end < req.start:
            return TriggerResponse(success=False, message=f"잘못된 범위: {req.start}~{req.end}")

        pages = (req.end - req.start + 1000) // 1000
        logger.info(
            f"[Playground] 🎯 Range Scan 트리거: {req.start:,}~{req.end:,} ({pages}p)"
        )

        async def _run_range_scan():
            from app.clients.foodsafety_api import ApiClient
            from app.repositories.state_repository import StateRepository
            from app.services.rolling_scanner import RollingScanner

            svc = "I2861"
            api_client = ApiClient()
            state_repo = StateRepository()
            scanner = RollingScanner(api_client, svc, state_repo)

            state = state_repo.load_state(svc)
            fingerprints = state.get("page_fingerprints", {})
            scan_times = state.get("page_scan_times", {})

            max_pages = pages

            # flush callback — scraper 파이프라인으로
            async def _flush(rows):
                from scraper import run_scraper_for_service_with_rows
                await run_scraper_for_service_with_rows(svc, rows, collected_by="range_scan")

            scanned, new_rows, mismatch, _ = await scanner._scan_range(
                svc, req.start, req.start, req.end,
                max_pages, fingerprints, scan_times, "RANGE"
            )

            if new_rows:
                await _flush(new_rows)
                logger.info(
                    f"[Playground] ✅ Range Scan 완료: {scanned}p, {len(new_rows)}건 수집"
                )
            else:
                logger.info(f"[Playground] ✅ Range Scan 완료: {scanned}p, 신규 0건")

            # 상태 저장 (fingerprints + scan_times 업데이트)
            state["page_fingerprints"] = fingerprints
            state["page_scan_times"] = scan_times
            state_repo.save_state(svc, state)

        import asyncio
        asyncio.create_task(_run_range_scan())

        return TriggerResponse(
            success=True,
            message=f"🎯 Range Scan 등록: {req.start:,}~{req.end:,} ({pages}p)"
        )
    except Exception as e:
        logger.error(f"[Playground] Range Scan 트리거 실패: {e}")
        return TriggerResponse(success=False, message=str(e))


@router.post("/trigger/{job_type}", response_model=TriggerResponse)
async def trigger_job(job_type: str):
    """지정한 잡을 즉시 실행합니다.
    
    job_type: scraper | rolling_scan | tail_ping | boost_scan
    """
    try:
        if job_type == "scraper":
            from app.core.scheduler import trigger_immediate_scrape
            trigger_immediate_scrape()
            return TriggerResponse(success=True, message="Scraper + Boost Scan 트리거 완료")

        elif job_type == "rolling_scan":
            from app.core.scheduler import scheduler, _scraper_job
            import time
            scheduler.add_job(
                _scraper_job, 'date',
                run_date=datetime.now(),
                id=f"manual_rolling_{int(time.time())}",
            )
            return TriggerResponse(success=True, message="Rolling Scan 즉시 실행 등록")

        elif job_type == "tail_ping":
            from app.services.tail_ping_job import run_tail_ping
            from app.core.scheduler import scheduler
            import time
            scheduler.add_job(
                run_tail_ping, 'date',
                run_date=datetime.now(),
                id=f"manual_tail_ping_{int(time.time())}",
            )
            return TriggerResponse(success=True, message="Tail Ping 즉시 실행 등록")

        elif job_type == "boost_scan":
            from app.core.scheduler import scheduler, _boosted_rolling_scan_job
            import time
            scheduler.add_job(
                _boosted_rolling_scan_job, 'date',
                run_date=datetime.now(),
                id=f"manual_boost_{int(time.time())}",
            )
            return TriggerResponse(success=True, message="🚀 Boost Scan (Random 50%) 즉시 실행 등록")

        elif job_type == "chng_dt_poll":
            # I2500 CHNG_DT Poller 즉시 실행
            async def _run_poller():
                from app.services.chng_dt_poller import poll_today_changes
                result = await poll_today_changes()
                logger.info(
                    f"[Playground] CHNG_DT Poller 완료: "
                    f"전체 {result['total']}건, 신규 {result['new']}건, 스킵 {result['skipped']}건"
                )

            asyncio.create_task(_run_poller())
            return TriggerResponse(success=True, message="📡 I2500 CHNG_DT Poller 즉시 실행 시작")

        else:
            raise HTTPException(status_code=400, detail=f"알 수 없는 잡 타입: {job_type}")
    except Exception as e:
        logger.error(f"[Playground] 트리거 실패: {e}")
        return TriggerResponse(success=False, message=str(e))



# ─── 페이지 스캔 히스토리 ────────────────────────────────────────────────────

@router.get("/page-scan-history/{service_id}", response_model=PageScanHistoryResponse)
async def get_page_scan_history(service_id: str = "I2861"):
    """page_fingerprints + page_scan_times를 페이지별 테이블로 변환하여 반환합니다."""
    from app.repositories.state_repository import StateRepository
    state_repo = StateRepository()
    state = state_repo.load_state(service_id)

    total_count = state.get("last_total_count", 0)
    fingerprints = state.get("page_fingerprints", {})
    scan_times = state.get("page_scan_times", {})
    total_pages = (total_count + 999) // 1000 if total_count > 0 else 0

    entries = []
    for p in range(total_pages):
        page_start = p * 1000 + 1
        fp = fingerprints.get(str(page_start))
        ts = scan_times.get(str(page_start))
        entries.append(PageScanEntry(
            page_number=p + 1,
            page_start=page_start,
            fingerprint=fp[:12] if fp else None,
            last_scanned=ts,
        ))

    scanned = sum(1 for e in entries if e.fingerprint is not None)

    return PageScanHistoryResponse(
        total_pages=total_pages,
        scanned_pages=scanned,
        entries=entries,
    )


# ─── 오늘 감지 현황 ──────────────────────────────────────────────────────────

@router.get("/today-detection/{service_id}", response_model=TodayDetectionResponse)
async def get_today_detection(service_id: str = "I2861"):
    """오늘 + 어제 CHNG_DT로 감지된 레코드 현황을 반환합니다."""
    from datetime import timedelta

    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    today_display = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y%m%d")
    yesterday_display = yesterday.strftime("%Y-%m-%d")

    with get_db() as conn:
        # 오늘 변동분
        today_count = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE last_event_date = ?",
            (today_str,)
        ).fetchone()[0]

        # 어제 변동분
        yesterday_count = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE last_event_date = ?",
            (yesterday_str,)
        ).fetchone()[0]

        # 전체 레코드
        total = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]

        # 최근 감지된 오늘+어제 데이터 (최신 10건)
        recent = conn.execute(
            """SELECT business_name, license_no, industry_type, last_event_date, 
                      updated_at, infer_update_type
               FROM businesses 
               WHERE last_event_date IN (?, ?) 
               ORDER BY last_event_date DESC, updated_at DESC 
               LIMIT 10""",
            (today_str, yesterday_str)
        ).fetchall()

        recent_list = [
            {
                "business_name": r["business_name"],
                "license_no": r["license_no"],
                "industry_type": r["industry_type"],
                "event_date": r["last_event_date"],
                "updated_at": r["updated_at"],
                "update_type": r["infer_update_type"],
            }
            for r in recent
        ]

    # 스캔 커버리지 계산
    from app.repositories.state_repository import StateRepository
    state_repo = StateRepository()
    state = state_repo.load_state(service_id)
    fingerprints = state.get("page_fingerprints", {})
    total_count = state.get("last_total_count", 0)
    total_pages = (total_count + 999) // 1000 if total_count > 0 else 0
    scanned_pages = len(fingerprints)
    coverage = (scanned_pages / total_pages * 100) if total_pages > 0 else 0

    return TodayDetectionResponse(
        today_date=today_display,
        today_count=today_count,
        yesterday_date=yesterday_display,
        yesterday_count=yesterday_count,
        total_records=total,
        scan_coverage_pct=round(coverage, 1),
        recent_detections=recent_list,
    )


# ─── Tail 히스토리 (일별 known_tail 추이) ────────────────────────────────────

@router.get("/tail-history/{service_id}", response_model=TailHistoryResponse)
async def get_tail_history(service_id: str = "I2861"):
    """최근 90일 known_tail 변화 추이를 반환합니다."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT record_date, total_count 
               FROM tail_history 
               WHERE service_id = ? 
               ORDER BY record_date DESC 
               LIMIT 90""",
            (service_id,)
        ).fetchall()

    entries = [
        TailHistoryEntry(record_date=r["record_date"], total_count=r["total_count"])
        for r in reversed(rows)  # 오래된 순 정렬
    ]

    return TailHistoryResponse(service_id=service_id, entries=entries)


# ─── CHNG_DT Poller 트렌드 ──────────────────────────────────────────────────

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


@router.get("/chng-dt-trend")
async def get_chng_dt_trend():
    """
    CHNG_DT Poller 시간별 트렌드 데이터.
    어제+오늘 날짜의 폴링 이력을 반환합니다.
    """
    from datetime import timedelta

    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y%m%d")

    with get_db() as conn:
        # 어제 + 오늘 이력 조회
        rows = conn.execute(
            """SELECT poll_date, polled_at, total_api_count, new_inserted,
                      already_exists, pages_fetched, elapsed_sec
               FROM chng_dt_poll_history
               WHERE poll_date IN (?, ?)
               ORDER BY polled_at ASC""",
            (yesterday_str, today_str)
        ).fetchall()

    # 날짜별로 그룹핑
    yesterday_entries = []
    today_entries = []
    for r in rows:
        entry = ChngDtPollEntry(
            polled_at=r["polled_at"],
            total_api_count=r["total_api_count"],
            new_inserted=r["new_inserted"],
            already_exists=r["already_exists"],
            pages_fetched=r["pages_fetched"],
            elapsed_sec=r["elapsed_sec"],
        )
        if r["poll_date"] == yesterday_str:
            yesterday_entries.append(entry)
        else:
            today_entries.append(entry)

    # 현재 시간대에 따라 주 대상 결정
    if now.hour >= 19:
        primary_date = today_str
        primary_entries = today_entries
    else:
        primary_date = yesterday_str
        primary_entries = yesterday_entries

    latest_total = primary_entries[-1].total_api_count if primary_entries else 0
    total_inserted = sum(e.new_inserted for e in primary_entries)

    return {
        "target_date": primary_date,
        "entries": [e.model_dump() for e in primary_entries],
        "latest_total": latest_total,
        "total_inserted": total_inserted,
        "yesterday_date": yesterday_str,
        "yesterday_entries": [e.model_dump() for e in yesterday_entries],
        "today_date": today_str,
        "today_entries": [e.model_dump() for e in today_entries],
    }
