import json
from datetime import datetime, timedelta
from database import get_db

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
