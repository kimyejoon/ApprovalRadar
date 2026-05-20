import asyncio
import json
import time
from datetime import datetime, timedelta
from database import get_db
from app.core.logger import logger
from app.repositories.state_repository import StateRepository

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


def trigger_range_scan_task(start: int, end: int):
    pages = (end - start + 1000) // 1000
    logger.info(
        f"[Playground] 🎯 Range Scan 트리거: {start:,}~{end:,} ({pages}p)"
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

        async def _flush(rows):
            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows(svc, rows, collected_by="range_scan")

        scanned, new_rows, mismatch, _ = await scanner._scan_range(
            svc, start, start, end,
            pages, fingerprints, scan_times, "RANGE"
        )

        if new_rows:
            await _flush(new_rows)
            logger.info(
                f"[Playground] ✅ Range Scan 완료: {scanned}p, {len(new_rows)}건 수집"
            )
        else:
            logger.info(f"[Playground] ✅ Range Scan 완료: {scanned}p, 신규 0건")

        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        state_repo.save_state(svc, state)

    asyncio.create_task(_run_range_scan())


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


def get_page_scan_history_data(service_id: str) -> dict:
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
        entries.append({
            "page_number": p + 1,
            "page_start": page_start,
            "fingerprint": fp[:12] if fp else None,
            "last_scanned": ts,
        })

    scanned = sum(1 for e in entries if e["fingerprint"] is not None)

    return {
        "total_pages": total_pages,
        "scanned_pages": scanned,
        "entries": entries,
    }


def get_today_detection_data(service_id: str) -> dict:
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    today_display = now.strftime("%Y-%m-%d")
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y%m%d")
    yesterday_display = yesterday.strftime("%Y-%m-%d")

    with get_db() as conn:
        today_count = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE last_event_date = ?",
            (today_str,)
        ).fetchone()[0]

        yesterday_count = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE last_event_date = ?",
            (yesterday_str,)
        ).fetchone()[0]

        total = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]

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

    state_repo = StateRepository()
    state = state_repo.load_state(service_id)
    fingerprints = state.get("page_fingerprints", {})
    total_count = state.get("last_total_count", 0)
    total_pages = (total_count + 999) // 1000 if total_count > 0 else 0
    scanned_pages = len(fingerprints)
    coverage = (scanned_pages / total_pages * 100) if total_pages > 0 else 0

    return {
        "today_date": today_display,
        "today_count": today_count,
        "yesterday_date": yesterday_display,
        "yesterday_count": yesterday_count,
        "total_records": total,
        "scan_coverage_pct": round(coverage, 1),
        "recent_detections": recent_list,
    }


def get_tail_history_data(service_id: str) -> dict:
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
        {"record_date": r["record_date"], "total_count": r["total_count"]}
        for r in reversed(rows)
    ]
    return {"service_id": service_id, "entries": entries}


def get_chng_dt_trend_data() -> dict:
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y%m%d")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT poll_date, polled_at, total_api_count, new_inserted,
                      already_exists, pages_fetched, elapsed_sec
               FROM chng_dt_poll_history
               WHERE poll_date IN (?, ?)
               ORDER BY polled_at ASC""",
            (yesterday_str, today_str)
        ).fetchall()

    yesterday_entries = []
    today_entries = []
    for r in rows:
        entry = {
            "polled_at": r["polled_at"],
            "total_api_count": r["total_api_count"],
            "new_inserted": r["new_inserted"],
            "already_exists": r["already_exists"],
            "pages_fetched": r["pages_fetched"],
            "elapsed_sec": r["elapsed_sec"],
        }
        if r["poll_date"] == yesterday_str:
            yesterday_entries.append(entry)
        else:
            today_entries.append(entry)

    if now.hour >= 19:
        primary_date = today_str
        primary_entries = today_entries
    else:
        primary_date = yesterday_str
        primary_entries = yesterday_entries

    latest_total = primary_entries[-1]["total_api_count"] if primary_entries else 0
    total_inserted = sum(e["new_inserted"] for e in primary_entries)

    return {
        "target_date": primary_date,
        "entries": primary_entries,
        "latest_total": latest_total,
        "total_inserted": total_inserted,
        "yesterday_date": yesterday_str,
        "yesterday_entries": yesterday_entries,
        "today_date": today_str,
        "today_entries": today_entries,
    }


def get_smart_sweep_status_data() -> dict:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT run_at, strategy, probe_calls, hot_segs, delta_segs,
                      collected, elapsed_sec, detail_json
               FROM smart_sweep_log
               ORDER BY id DESC LIMIT 10"""
        ).fetchall()

    entries = []
    for r in rows:
        detail = []
        try:
            detail = json.loads(r["detail_json"]) if r["detail_json"] else []
        except Exception:
            pass
        entries.append({
            "run_at": r["run_at"],
            "strategy": r["strategy"],
            "probe_calls": r["probe_calls"],
            "hot_segs": r["hot_segs"],
            "delta_segs": r["delta_segs"],
            "collected": r["collected"],
            "elapsed_sec": r["elapsed_sec"],
            "detail": detail,
        })

    return {"entries": entries, "count": len(entries)}


def get_smart_sweep_cache_data() -> dict:
    today = datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT seg_start, seg_end, total_count, first_chng, probed_at, probe_label
               FROM smart_sweep_cache
               ORDER BY seg_start ASC"""
        ).fetchall()

    result = []
    for r in rows:
        first_chng = r["first_chng"] or ""
        cls = "COLD"
        if first_chng >= today:
            cls = "HOT"
        elif first_chng >= yesterday:
            cls = "WARM"
        result.append({
            "seg": f"{r['seg_start']:,}~{r['seg_end']:,}",
            "total_count": r["total_count"],
            "first_chng": first_chng,
            "cls": cls,
            "probed_at": r["probed_at"],
            "label": r["probe_label"],
        })

    hot = sum(1 for x in result if x["cls"] == "HOT")
    warm = sum(1 for x in result if x["cls"] == "WARM")
    return {
        "total_cached": len(result),
        "hot": hot,
        "warm": warm,
        "cold": len(result) - hot - warm,
        "segments": result,
    }
