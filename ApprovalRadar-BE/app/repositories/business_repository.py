import json
from typing import List, Dict, Any, Optional, Tuple
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db

class BusinessRepository:
    def _build_where_clause(self, search: Optional[str], start_date: Optional[str], end_date: Optional[str], regions: Optional[List[str]]) -> Tuple[str, List[Any]]:
        query_conditions = []
        params = []
        
        if search:
            query_conditions.append("(business_name LIKE ? OR license_no LIKE ?)")
            search_term = f"%{search}%"
            params.extend([search_term, search_term])
            
        if start_date:
            query_conditions.append("last_event_date >= ?")
            params.append(start_date)
            
        if end_date:
            query_conditions.append("last_event_date <= ?")
            params.append(end_date)
            
        if regions:
            region_conditions = []
            for r in regions:
                region_conditions.append("address LIKE ?")
                params.append(f"%{r}%")
            if region_conditions:
                query_conditions.append(f"({' OR '.join(region_conditions)})")
        
        where_clause = ""
        if query_conditions:
            where_clause = " WHERE " + " AND ".join(query_conditions)
            
        return where_clause, params

    def get_approvals(self, page: int, size: int, search: Optional[str], start_date: Optional[str], end_date: Optional[str], regions: Optional[List[str]], sort_by: str, sort_order: str) -> Tuple[List[Dict[str, Any]], int]:
        with get_db() as conn:
            cursor = conn.cursor()
            
            where_clause, params = self._build_where_clause(search, start_date, end_date, regions)
            
            # 전체 개수
            cursor.execute(f"SELECT COUNT(*) FROM businesses{where_clause}", params)
            total_count = cursor.fetchone()[0]
            
            # 정렬 및 페이징
            valid_sort_columns = ["created_at", "last_event_date", "updated_at", "license_date", "business_name"]
            if sort_by not in valid_sort_columns:
                sort_by = "created_at"
            order = "ASC" if sort_order.lower() == "asc" else "DESC"
            
            offset = (page - 1) * size
            data_query = f"SELECT * FROM businesses{where_clause} ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
            
            cursor.execute(data_query, params + [size, offset])
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                record = dict(row)
                try:
                    record["representative_history"] = json.loads(record.get("representative_history", "[]"))
                    record["licensing_history"] = json.loads(record.get("licensing_history", "[]"))
                except Exception:
                    record["representative_history"] = []
                    record["licensing_history"] = []
                result.append(record)
                
            return result, total_count

    def get_indicators(self, search: Optional[str], start_date: Optional[str], end_date: Optional[str], regions: Optional[List[str]]) -> Tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        with get_db() as conn:
            cursor = conn.cursor()
            where_clause, params = self._build_where_clause(search, start_date, end_date, regions)
            
            # 1. Total approvals
            cursor.execute(f"SELECT COUNT(*) FROM businesses{where_clause}", params)
            total_approvals = cursor.fetchone()[0]
            
            # 2. Status distribution
            status_query = f"SELECT COALESCE(business_status, '상태없음') as name, COUNT(*) as value FROM businesses{where_clause} GROUP BY name"
            cursor.execute(status_query, params)
            status_distribution = [{"name": row[0], "value": row[1]} for row in cursor.fetchall()]
            
            # 3. Trend chart
            trend_where = where_clause + (" AND " if where_clause else " WHERE ") + "last_event_date IS NOT NULL AND last_event_date != ''"
            trend_query = f"SELECT substr(last_event_date, 1, 10) as date, COUNT(*) as count FROM businesses{trend_where} GROUP BY date ORDER BY date ASC"
            cursor.execute(trend_query, params)
            trend_chart = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            return total_approvals, status_distribution, trend_chart

    def get_business_by_license_no(self, license_no: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM businesses WHERE license_no = ?", (license_no,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def insert_business(self, record: dict):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO businesses 
                (license_no, business_name, address, representative_name, business_status, license_date, phone_number, last_event_date, is_new)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (
                record["license_no"], record["business_name"], record["address"], 
                record["representative_name"], record["business_status"], 
                record["license_date"], record["phone_number"], record["last_event_date"]
            ))
            conn.commit()

    def update_business(self, license_no: str, updates: dict):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE businesses 
                SET business_name = ?, address = ?, representative_name = ?, 
                    business_status = ?, phone_number = ?,
                    representative_history = ?, licensing_history = ?,
                    last_event_date = ?,
                    updated_at = ?, is_new = 1
                WHERE license_no = ?
            ''', (
                updates["business_name"], updates["address"], updates["representative_name"], 
                updates["business_status"], updates["phone_number"],
                updates["representative_history"], updates["licensing_history"],
                updates["last_event_date"], updates["updated_at"], license_no
            ))
            conn.commit()
