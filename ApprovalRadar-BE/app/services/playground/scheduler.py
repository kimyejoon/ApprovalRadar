import asyncio
import time
from datetime import datetime
from app.core.logger import logger

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
    if job_type == "scraper":
        from app.core.scheduler import trigger_immediate_scrape
        trigger_immediate_scrape()
        return "Scraper + Boost Scan 트리거 완료"

    elif job_type == "oldest_first_scan":
        def _run_oldest_first():
            import asyncio as _asyncio
            from app.core.config import settings as _s
            from app.clients.foodsafety_api import ApiClient
            from app.repositories.state_repository import StateRepository
            from app.services.rolling_scanner import RollingScanner

            async def _inner():
                svc_ids = getattr(_s, "SERVICES", ["I2861"])
                async with ApiClient() as api_client:
                    for svc_id in svc_ids:
                        state_repo = StateRepository()
                        scanner = RollingScanner(api_client, svc_id, state_repo)

                        async def flush_cb(rows):
                            from scraper import run_scraper_for_service_with_rows
                            await run_scraper_for_service_with_rows(
                                svc_id, rows, collected_by="oldest_first_manual"
                            )

                        await scanner._scan_oldest_first(flush_callback=flush_cb)

            _asyncio.run(_inner())

        from app.core.scheduler import scheduler
        scheduler.add_job(
            _run_oldest_first, 'date',
            run_date=datetime.now(),
            id=f"manual_oldest_first_{int(time.time())}",
        )
        return "Oldest-First Scan 즉시 실행 등록 (연식 1h↑ 우선)"

    elif job_type == "rolling_scan":
        from app.core.scheduler import scheduler, _scraper_job
        scheduler.add_job(
            _scraper_job, 'date',
            run_date=datetime.now(),
            id=f"manual_rolling_{int(time.time())}",
        )
        return "Scraper (DiffCrawler) 즉시 실행 등록"

    elif job_type == "tail_ping":
        from app.services.tail_ping_job import run_tail_ping
        from app.core.scheduler import scheduler
        scheduler.add_job(
            run_tail_ping, 'date',
            run_date=datetime.now(),
            id=f"manual_tail_ping_{int(time.time())}",
        )
        return "Tail Ping 즉시 실행 등록"

    elif job_type == "chng_dt_poll":
        async def _run_poller():
            from app.services.chng_dt_poller import poll_today_changes
            result = await poll_today_changes()
            logger.info(
                f"[Playground] CHNG_DT Poller 완료: "
                f"전체 {result['total']}건, 신규 {result['new']}건, 스킵 {result['skipped']}건"
            )
        asyncio.create_task(_run_poller())
        return "📡 I2500 CHNG_DT Poller 즉시 실행 시작"

    elif job_type == "smart_sweep_micro":
        async def _run_sweep():
            from app.clients.foodsafety_api import ApiClient
            from app.services.smart_sweep import SmartSweepService
            async with ApiClient() as api_client:
                svc = SmartSweepService(api_client)
                await svc.run_micro_probe()
        asyncio.create_task(_run_sweep())
        return "🔍 SmartSweep Micro Probe 즉시 실행 시작"

    elif job_type == "smart_sweep_full":
        async def _run_full_sweep():
            from app.clients.foodsafety_api import ApiClient
            from app.services.smart_sweep import SmartSweepService
            async with ApiClient() as api_client:
                svc = SmartSweepService(api_client)
                await svc.run_full_sweep(max_segs=200)
        asyncio.create_task(_run_full_sweep())
        return "🔄 SmartSweep Full Sweep 즉시 실행 시작 (200seg)"

    else:
        raise ValueError(f"알 수 없는 잡 타입: {job_type}")
