import json
import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db

class StateRepository:
    def load_state(self, service_id: str) -> dict:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT last_total_count, pivots, extra_state FROM crawler_state WHERE service_id = ?", (service_id,))
                row = cursor.fetchone()
                if row:
                    extra = json.loads(row["extra_state"] or "{}")
                    state = {
                        "last_total_count": row["last_total_count"],
                        "pivots": json.loads(row["pivots"] or "{}"),
                        **extra   # _bootstrapping, empty_pivot_cycles, cb_consecutive_count 복원
                    }
                    return state
        except Exception as e:
            from app.core.logger import logger
            logger.error(f"Error loading state from DB for {service_id}: {e}")

        return {
            "last_total_count": 0,
            "pivots": {}
        }

    def save_state(self, service_id: str, state: dict):
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                now = datetime.datetime.now().isoformat()
                # last_total_count, pivots 외 나머지 필드를 extra_state JSON으로 저장
                extra = {k: v for k, v in state.items()
                         if k not in ("last_total_count", "pivots")}
                cursor.execute('''
                    INSERT OR REPLACE INTO crawler_state
                    (service_id, last_total_count, pivots, extra_state, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    service_id,
                    state.get("last_total_count", 0),
                    json.dumps(state.get("pivots", {}), ensure_ascii=False),
                    json.dumps(extra, ensure_ascii=False),
                    now
                ))
                conn.commit()
        except Exception as e:
            from app.core.logger import logger
            logger.error(f"Error saving state to DB for {service_id}: {e}")
