import asyncio
import time
from datetime import datetime
from app.core.logger import logger

JOB_NAMES = {
    "scraper_job": "🔍 Scraper (Oldest-First Scan)",
    "key_recovery_job": "🔑 키 회복 체크 (10분)",
    "backfill_job": "📋 업종 백필 (6시간)",
    "vacuum_job": "🗑️ DB 최적화 (일요일 3시)",
    "backup_job": "💾 DB 백업 (매일 4시)",
}

def get_scheduler_status_data() -> dict:
    from app.core.scheduler import scheduler
    now = datetime.now()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        remaining = None
        if next_run:
            remaining = (next_run.replace(tzinfo=None) - now).total_seconds()

        jobs.append({
            "job_id": job.id,
            "name": JOB_NAMES.get(job.id, job.id),
            "next_run": next_run.strftime("%H:%M:%S") if next_run else None,
            "seconds_remaining": round(remaining, 1) if remaining else None,
            "is_running": False,
        })

    jobs.sort(key=lambda j: j["seconds_remaining"] if j["seconds_remaining"] is not None else 99999)
    return {
        "jobs": jobs,
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def trigger_job_task(job_type: str) -> str:
    if job_type in ("scraper", "rolling_scan"):
        from app.core.scheduler import trigger_immediate_scrape
        trigger_immediate_scrape()
        return "Scraper (Oldest-First Scan) 즉시 실행 등록 완료"

    elif job_type == "chng_dt_poll":
        async def _run_poller():
            from app.services.chng_dt_poller import _run_poller_async
            await _run_poller_async()
            logger.info("[Playground] CHNG_DT Poller 수동 실행 완료")
        asyncio.create_task(_run_poller())
        return "📡 I2500 CHNG_DT Poller 즉시 실행 시작"

    else:
        raise ValueError(f"알 수 없는 잡 타입: {job_type}. 사용 가능: scraper, rolling_scan, chng_dt_poll")
