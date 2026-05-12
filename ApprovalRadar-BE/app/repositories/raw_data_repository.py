import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db

class RawDataRepository:
    def insert_raw_data(self, license_no: str, raw_json: str, fetched_at: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO api_raw_data (license_no, raw_json, fetched_at)
                VALUES (?, ?, ?)
            ''', (license_no, raw_json, fetched_at))
            conn.commit()
