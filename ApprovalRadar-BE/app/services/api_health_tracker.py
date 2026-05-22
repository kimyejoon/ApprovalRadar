"""
API 건강 상태 트래커.

식품안전나라 OpenAPI의 응답 품질을 실시간으로 집계하여
4단계 상태(NORMAL / SLOW / DEGRADED / UNSTABLE)를 산출합니다.

이벤트 소스:
  - foodsafety_api.py 에서 record_* 메서드를 호출
  - 롤링 윈도우(WINDOW_SECONDS=300초) 내의 이벤트만 유효

DB 저장:
  - 상태 변경 시 즉시 + 5분 주기 저장 (api_health_log 테이블)
  - 추후 시간대별 서버 불안정 Bar Chart 분석에 활용
"""
import threading
import time
from collections import deque
from datetime import datetime


# ─── 상태 상수 ────────────────────────────────────────────────────────────────
STATUS_NORMAL   = "NORMAL"     # 정상 (초록)
STATUS_SLOW     = "SLOW"       # 느림 (노란)
STATUS_DEGRADED = "DEGRADED"   # 저하 (주황)
STATUS_UNSTABLE = "UNSTABLE"   # 불안정 (빨강)

WINDOW_SECONDS     = 300   # 5분 롤링 윈도우
DB_SAVE_INTERVAL   = 300   # 정기 DB 저장 간격 (초)


class ApiHealthTracker:
    """Thread-safe 단일 인스턴스 트래커."""

    def __init__(self):
        self._lock = threading.Lock()
        # (timestamp, event_type, duration_ms, service_id)
        self._events: deque = deque()
        self._current_status: str = STATUS_NORMAL
        self._status_changed_at: str = datetime.now().isoformat()
        self._last_db_save: float = 0.0

    # ─── 이벤트 기록 메서드 (foodsafety_api.py 에서 호출) ─────────────────────

    def record_success(self, duration_ms: float, service_id: str = "") -> None:
        with self._lock:
            self._events.append((time.time(), "success", duration_ms, service_id))
            self._flush_and_update()

    def record_timeout(self, service_id: str = "") -> None:
        with self._lock:
            self._events.append((time.time(), "timeout", 0.0, service_id))
            self._flush_and_update()

    def record_waf_block(self, service_id: str = "") -> None:
        with self._lock:
            self._events.append((time.time(), "waf_block", 0.0, service_id))
            self._flush_and_update()

    def record_max_retry(self, service_id: str = "") -> None:
        with self._lock:
            self._events.append((time.time(), "max_retry", 0.0, service_id))
            self._flush_and_update()

    # ─── 내부 로직 ────────────────────────────────────────────────────────────

    def _flush_and_update(self) -> None:
        """오래된 이벤트 제거 후 상태 재계산. _lock 보유 상태에서 호출."""
        cutoff = time.time() - WINDOW_SECONDS
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

        metrics = self._compute_metrics()
        new_status = self._compute_status(metrics)

        changed = new_status != self._current_status
        if changed:
            self._current_status = new_status
            self._status_changed_at = datetime.now().isoformat()

        # DB 저장: 상태 변경 시 즉시 / 아니면 5분 주기
        if changed or (time.time() - self._last_db_save >= DB_SAVE_INTERVAL):
            self._save_to_db(metrics, new_status)

    def _compute_metrics(self) -> dict:
        events = list(self._events)
        timeouts   = sum(1 for e in events if e[1] == "timeout")
        waf_blocks = sum(1 for e in events if e[1] == "waf_block")
        max_retries= sum(1 for e in events if e[1] == "max_retry")
        durations  = [e[2] for e in events if e[1] == "success"]
        total      = len(events)
        avg_ms     = (sum(durations) / len(durations)) if durations else 0.0
        success_rate = (len(durations) / total * 100) if total > 0 else 100.0
        return {
            "timeout_count":   timeouts,
            "waf_block_count": waf_blocks,
            "max_retry_count": max_retries,
            "avg_response_ms": round(avg_ms),
            "total_calls":     total,
            "success_count":   len(durations),
            "success_rate":    round(success_rate, 1),
        }

    @staticmethod
    def _compute_status(m: dict) -> str:
        if m["max_retry_count"] > 0 or m["waf_block_count"] >= 3:
            return STATUS_UNSTABLE
        if m["waf_block_count"] > 0 or m["timeout_count"] >= 5 or m["avg_response_ms"] > 60_000:
            return STATUS_DEGRADED
        if m["timeout_count"] >= 2 or m["avg_response_ms"] > 10_000:
            return STATUS_SLOW
        return STATUS_NORMAL

    def _save_to_db(self, metrics: dict, status: str) -> None:
        try:
            from database import get_db
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO api_health_log
                       (recorded_at, status, avg_response_ms,
                        timeout_count, waf_block_count, max_retry_count,
                        total_calls, success_rate, window_seconds)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        datetime.now().isoformat(),
                        status,
                        metrics["avg_response_ms"],
                        metrics["timeout_count"],
                        metrics["waf_block_count"],
                        metrics["max_retry_count"],
                        metrics["total_calls"],
                        metrics["success_rate"],
                        WINDOW_SECONDS,
                    )
                )
                conn.commit()
            self._last_db_save = time.time()
        except Exception:
            pass  # DB 저장 실패는 무시 (메인 로직 방해 안 함)

    # ─── 외부 조회 ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """현재 상태 + 메트릭 반환 (API 엔드포인트용)."""
        with self._lock:
            cutoff = time.time() - WINDOW_SECONDS
            while self._events and self._events[0][0] < cutoff:
                self._events.popleft()
            metrics = self._compute_metrics()
            return {
                "status": self._current_status,
                "status_changed_at": self._status_changed_at,
                "window_seconds": WINDOW_SECONDS,
                "metrics": metrics,
            }

    def get_history(self, limit: int = 48) -> list:
        """DB에서 최근 기록 반환 (Bar Chart용)."""
        try:
            from database import get_db
            with get_db() as conn:
                rows = conn.execute(
                    """SELECT recorded_at, status, avg_response_ms,
                              timeout_count, waf_block_count, total_calls, success_rate
                       FROM api_health_log
                       ORDER BY id DESC LIMIT ?""",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in reversed(rows)]
        except Exception:
            return []


# ─── 프로세스 전역 싱글톤 ─────────────────────────────────────────────────────
health_tracker = ApiHealthTracker()
