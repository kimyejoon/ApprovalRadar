from datetime import datetime
from database import get_db
from app.services.smart_sweep.result import SweepResult

def _load_cache(probes: list[tuple[int, int]]) -> dict[tuple[int, int], int | None]:
    """세그먼트별 이전 total_count를 DB에서 로드."""
    result = {}
    if not probes:
        return result
    with get_db() as conn:
        for seg_start, seg_end in probes:
            row = conn.execute(
                "SELECT total_count FROM smart_sweep_cache WHERE seg_start=? AND seg_end=?",
                (seg_start, seg_end)
            ).fetchone()
            result[(seg_start, seg_end)] = row["total_count"] if row else None
    return result

def _save_cache(seg_start: int, seg_end: int, total: int, first_chng: str, label: str):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO smart_sweep_cache
               (seg_start, seg_end, total_count, first_chng, probed_at, probe_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (seg_start, seg_end, total, first_chng, datetime.now().isoformat(), label)
        )

def _batch_save_cache(entries: list[dict], label: str):
    """여러 세그먼트 캐시를 1회 트랜잭션으로 일괄 저장 (WAL 누적 방지)."""
    if not entries:
        return
    now = datetime.now().isoformat()
    rows = [
        (e["seg_start"], e["seg_end"], 0, e.get("first_chng", ""), now, label)
        # total_count=0 고정 (delta 전략 폐기로 total 캐싱 불필요)
        for e in entries
    ]
    with get_db() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO smart_sweep_cache
               (seg_start, seg_end, total_count, first_chng, probed_at, probe_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows
        )

def _save_log(result: SweepResult):
    row = result.to_log_row()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO smart_sweep_log
               (run_at, strategy, probe_calls, hot_segs, delta_segs, collected, elapsed_sec, detail_json)
               VALUES (:run_at,:strategy,:probe_calls,:hot_segs,:delta_segs,:collected,:elapsed_sec,:detail_json)""",
            row
        )
