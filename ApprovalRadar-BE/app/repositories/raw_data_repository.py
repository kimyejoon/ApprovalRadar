import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db

class RawDataRepository:
    def insert_raw_data(self, license_no: str, raw_json: str, fetched_at: str, conn=None):
        query = '''
            INSERT OR REPLACE INTO api_raw_data (license_no, raw_json, fetched_at)
            VALUES (?, ?, ?)
        '''
        params = (license_no, raw_json, fetched_at)
        
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def insert_raw_data_batch(self, raw_list: list, conn=None):
        query = '''
            INSERT OR REPLACE INTO api_raw_data (license_no, raw_json, fetched_at)
            VALUES (?, ?, ?)
        '''
        if conn:
            conn.executemany(query, raw_list)
        else:
            with get_db() as c:
                c.executemany(query, raw_list)
                c.commit()
