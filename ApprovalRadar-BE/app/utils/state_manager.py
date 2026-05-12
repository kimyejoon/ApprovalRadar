import json
import datetime
import sys
import os

# root 디렉터리의 database 모듈 임포트 지원
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db

class StateManager:
    @staticmethod
    def load_state() -> dict:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT last_total_count, pivots FROM crawler_state WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return {
                        "last_total_count": row["last_total_count"],
                        "pivots": json.loads(row["pivots"] or "{}")
                    }
        except Exception as e:
            print(f"Error loading state from DB: {e}")
            
        return {
            "last_total_count": 0,
            "pivots": {}
        }

    @staticmethod
    def save_state(state: dict):
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                now = datetime.datetime.now().isoformat()
                cursor.execute('''
                    INSERT OR REPLACE INTO crawler_state (id, last_total_count, pivots, updated_at)
                    VALUES (1, ?, ?, ?)
                ''', (state.get("last_total_count", 0), json.dumps(state.get("pivots", {}), ensure_ascii=False), now))
                conn.commit()
        except Exception as e:
            print(f"Error saving state to DB: {e}")

