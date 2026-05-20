import json
from datetime import datetime

class SweepResult:
    def __init__(self):
        self.strategy: str = ""
        self.probe_calls: int = 0
        self.segments: list[dict] = []      # 탐침 결과 전체
        self.hot_segs: list[dict] = []      # HOT 세그먼트
        self.collected: int = 0
        self.elapsed_sec: float = 0.0
        self.run_at: str = datetime.now().isoformat()

    def to_log_row(self) -> dict:
        return {
            "run_at": self.run_at,
            "strategy": self.strategy,
            "probe_calls": self.probe_calls,
            "hot_segs": len(self.hot_segs),
            "delta_segs": 0,  # 폐기됨 (total_count delta 불신뢰)
            "collected": self.collected,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "detail_json": json.dumps(
                [{"seg": f"{s['seg_start']}/{s['seg_end']}", "class": s["cls"],
                  "first_chng": s.get("first_chng")}
                 for s in self.segments if s.get("cls") != "COLD"],
                ensure_ascii=False
            ),
        }
