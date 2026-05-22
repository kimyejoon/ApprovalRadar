import json
from typing import List, Dict, Any, Optional, Tuple
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db
from app.repositories.base import AbstractBusinessRepository
from app.repositories.query_builder import build_business_where_clause
from app.repositories.indicator_repository import IndicatorRepository

class BusinessRepository(AbstractBusinessRepository):
    def get_approvals(self, page: int, size: int, search: Optional[str], start_date: Optional[str], end_date: Optional[str], regions: Optional[List[str]], sort_by: str, sort_order: str, infer_update_type: Optional[List[str]] = None, industry_type: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], int]:
        with get_db() as conn:
            cursor = conn.cursor()
            
            where_clause, params = build_business_where_clause(search, start_date, end_date, regions, infer_update_type, industry_type)
            
            # 전체 개수
            cursor.execute(f"SELECT COUNT(*) FROM businesses{where_clause}", params)
            total_count = cursor.fetchone()[0]
            
            # 정렬 기준 컬럼 맵핑
            if sort_by == "phone":
                sort_by = "phone_number"
            elif sort_by == "date":
                sort_by = "last_event_date"
                
            valid_sort_columns = [
                "created_at", "last_event_date", "updated_at", "license_date", 
                "business_name", "phone_number", "representative_name", 
                "business_status", "license_no", "industry_type"
            ]
            if sort_by not in valid_sort_columns:
                sort_by = "created_at"
            order = "ASC" if sort_order.lower() == "asc" else "DESC"
            
            offset = (page - 1) * size
            # last_event_date 정렬 시: 날짜 1차 → created_at 2차 (동일 날짜 내 수집순)
            # 다른 컬럼 정렬 시에도 created_at을 동일 방향 보조 정렬로 추가
            if sort_by == "last_event_date":
                order_clause = f"last_event_date {order}, created_at {order}"
            else:
                order_clause = f"{sort_by} {order}, created_at {order}"
            data_query = f"SELECT * FROM businesses{where_clause} ORDER BY {order_clause} LIMIT ? OFFSET ?"
            
            cursor.execute(data_query, params + [size, offset])
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                record = dict(row)
                result.append(record)
                
            return result, total_count

    def get_indicators(self, start_date: Optional[str], end_date: Optional[str]) -> Tuple[int, int, int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        # IndicatorRepository에 위임
        return IndicatorRepository().get_indicators(start_date, end_date)

    def get_business_by_license_no(self, license_no: str, conn=None) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM businesses WHERE license_no = ?"
        params = (license_no,)
        
        if conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        else:
            with get_db() as c:
                cursor = c.execute(query, params)
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None

    def get_businesses_by_date_and_name(self, license_date: str, business_name: str, conn=None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM businesses WHERE license_date = ? AND business_name = ? ORDER BY created_at DESC"
        params = (license_date, business_name)
        
        if conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            with get_db() as c:
                cursor = c.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def get_businesses_by_license_no(self, license_no: str, conn=None) -> List[Dict[str, Any]]:
        """인허가번호 기반 이력 조회 — 상호변경/미색인과 무관하게 정확 매칭."""
        query = "SELECT * FROM businesses WHERE license_no = ? ORDER BY last_event_date DESC, created_at DESC"
        if conn:
            cursor = conn.execute(query, (license_no,))
            return [dict(row) for row in cursor.fetchall()]
        else:
            with get_db() as c:
                cursor = c.execute(query, (license_no,))
                return [dict(row) for row in cursor.fetchall()]

    def insert_business(self, record: dict, conn=None):
        query = '''
            INSERT INTO businesses 
            (license_no, business_name, address, representative_name, business_status, license_date, phone_number, industry_type, last_event_date, is_new, update_type, prev_business_status, prev_representative_name, prev_business_name, infer_update_type, infer_update_detail, last_event_time, license_time, change_reason, change_before, change_after, collected_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            record["license_no"], record["business_name"], record["address"], 
            record["representative_name"], record["business_status"], 
            record["license_date"], record["phone_number"], record.get("industry_type"), record["last_event_date"],
            record.get("update_type"), record.get("prev_business_status"), 
            record.get("prev_representative_name"), record.get("prev_business_name"), record.get("infer_update_type"), record.get("infer_update_detail"),
            record.get("last_event_time"), record.get("license_time"),
            record.get("change_reason"), record.get("change_before"), record.get("change_after"),
            record.get("collected_by")
        )
        
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def update_business(self, license_no: str, updates: dict, conn=None):
        query = '''
            UPDATE businesses 
            SET business_name = ?, address = ?, representative_name = ?, 
                business_status = ?, phone_number = ?,
                industry_type = COALESCE(?, industry_type),
                representative_history = ?, licensing_history = ?,
                update_type = ?, prev_business_status = ?, prev_representative_name = ?, prev_business_name = ?,
                infer_update_type = ?, infer_update_detail = ?,
                last_event_date = ?, last_event_time = ?, license_time = ?,
                updated_at = ?, is_new = 1
            WHERE license_no = ?
        '''
        params = (
            updates["business_name"], updates["address"], updates["representative_name"], 
            updates["business_status"], updates["phone_number"], updates.get("industry_type"),
            updates["representative_history"], updates["licensing_history"],
            updates.get("update_type"), updates.get("prev_business_status"), updates.get("prev_representative_name"), updates.get("prev_business_name"),
            updates.get("infer_update_type"), updates.get("infer_update_detail"),
            updates["last_event_date"], updates.get("last_event_time"), updates.get("license_time"),
            updates["updated_at"], license_no
        )
        
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def update_business_by_key(self, license_no: str, last_event_date: str, updates: dict, conn=None):
        query = '''
            UPDATE businesses 
            SET business_name = ?, address = ?, representative_name = ?, 
                business_status = ?, phone_number = ?,
                industry_type = COALESCE(?, industry_type),
                representative_history = ?, licensing_history = ?,
                update_type = ?, prev_business_status = ?, prev_representative_name = ?, prev_business_name = ?,
                infer_update_type = ?, infer_update_detail = ?,
                last_event_time = ?, license_time = ?,
                updated_at = ?, is_new = 1
            WHERE license_no = ? AND last_event_date = ?
        '''
        params = (
            updates["business_name"], updates["address"], updates["representative_name"], 
            updates["business_status"], updates["phone_number"], updates.get("industry_type"),
            updates["representative_history"], updates["licensing_history"],
            updates.get("update_type"), updates.get("prev_business_status"), updates.get("prev_representative_name"), updates.get("prev_business_name"),
            updates.get("infer_update_type"), updates.get("infer_update_detail"),
            updates.get("last_event_time"), updates.get("license_time"),
            updates["updated_at"], license_no, last_event_date
        )
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def update_industry_type(self, license_no: str, industry_type: str, conn=None):
        query = "UPDATE businesses SET industry_type = ? WHERE license_no = ?"
        params = (industry_type, license_no)
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def update_from_i2500(
        self,
        license_no: str,
        industry_type: str = "",
        representative_name: str = "",
        phone_number: str = "",
        license_date: str = "",
        conn=None,
    ):
        """
        I2500 API 백필 결과 반영.
        - 이미 값이 있는 필드는 덮어쓰지 않음 (COALESCE)
        - 빈 문자열은 NULL로 처리하여 기존값 보호
        - license_date: None/미색인/빈값만 채움
        """
        query = """
            UPDATE businesses
            SET
                industry_type      = COALESCE(NULLIF(?, ''), industry_type),
                representative_name = COALESCE(
                    CASE WHEN representative_name = '' OR representative_name IS NULL
                         THEN NULLIF(?, '') ELSE representative_name END,
                    representative_name
                ),
                phone_number       = COALESCE(
                    CASE WHEN phone_number = '' OR phone_number IS NULL
                         THEN NULLIF(?, '') ELSE phone_number END,
                    phone_number
                ),
                license_date       = COALESCE(
                    CASE WHEN license_date IS NULL OR license_date = '' OR license_date = '미색인'
                         THEN NULLIF(?, '') ELSE license_date END,
                    license_date
                )
            WHERE license_no = ?
        """
        params = (industry_type, representative_name, phone_number, license_date, license_no)
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def update_read_info(self, license_no: str, conn=None):
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = "UPDATE businesses SET is_read = 1, read_at = ? WHERE license_no = ?"
        params = (now_str, license_no)
        if conn:
            conn.execute(query, params)
        else:
            with get_db() as c:
                c.execute(query, params)
                c.commit()

    def update_businesses_batch(self, update_list: list, conn=None):
        query = '''
            UPDATE businesses 
            SET business_name = ?, address = ?, representative_name = ?, 
                business_status = ?, phone_number = ?,
                industry_type = COALESCE(?, industry_type),
                representative_history = ?, licensing_history = ?,
                update_type = ?, prev_business_status = ?, prev_representative_name = ?, prev_business_name = ?,
                infer_update_type = ?, infer_update_detail = ?,
                last_event_time = ?, license_time = ?,
                updated_at = ?, is_new = 1
            WHERE license_no = ? AND last_event_date = ? AND COALESCE(change_before, '') = ?
        '''
        if conn:
            conn.executemany(query, update_list)
        else:
            with get_db() as c:
                c.executemany(query, update_list)
                c.commit()

    def insert_businesses_batch(self, insert_list: list, conn=None):
        query = '''
            INSERT INTO businesses 
            (license_no, business_name, address, representative_name, business_status, license_date, phone_number, industry_type, last_event_date, is_new, update_type, prev_business_status, prev_representative_name, prev_business_name, infer_update_type, infer_update_detail, last_event_time, license_time, change_reason, change_before, change_after, collected_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        if conn:
            conn.executemany(query, insert_list)
        else:
            with get_db() as c:
                c.executemany(query, insert_list)
                c.commit()



