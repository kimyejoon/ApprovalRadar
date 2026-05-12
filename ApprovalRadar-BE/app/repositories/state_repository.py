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
                cursor.execute("SELECT last_total_count, pivots FROM crawler_state WHERE service_id = ?", (service_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "last_total_count": row["last_total_count"],
                        "pivots": json.loads(row["pivots"] or "{}")
                    }
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
                cursor.execute('''
                    INSERT OR REPLACE INTO crawler_state (service_id, last_total_count, pivots, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (service_id, state.get("last_total_count", 0), json.dumps(state.get("pivots", {}), ensure_ascii=False), now))
                conn.commit()
        except Exception as e:
            from app.core.logger import logger
            logger.error(f"Error saving state to DB for {service_id}: {e}")
