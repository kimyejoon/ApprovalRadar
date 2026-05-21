from datetime import datetime, timedelta
from database import get_db
from app.repositories.state_repository import StateRepository

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


def get_chng_dt_trend_data() -> dict:
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y%m%d")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT poll_date, polled_at, total_api_count, new_inserted,
                      already_exists, pages_fetched, elapsed_sec,
                      COALESCE(api_raw_total_count, 0) as api_raw_total_count
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
            "api_raw_total_count": r["api_raw_total_count"],  # I2500 API 실제 total_count
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
