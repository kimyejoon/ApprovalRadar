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
                result.append(record)
                
            return result, total_count

    def get_indicators(self, start_date: Optional[str], end_date: Optional[str]) -> Tuple[int, int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        with get_db() as conn:
            cursor = conn.cursor()
            # 파라미터가 없으므로 search, regions는 None 전달
            where_clause, params = self._build_where_clause(None, start_date, end_date, None)
            
            # 1. Total approvals (Over the entire date range)
            cursor.execute(f"SELECT COUNT(*) FROM businesses{where_clause}", params)
            total_approvals = cursor.fetchone()[0]

            # 1.5 Today approvals (Target Day Only)
            target_date = end_date
            if not target_date:
                from datetime import datetime
                target_date = datetime.now().strftime('%Y%m%d')
                
            today_where_clause, today_params = self._build_where_clause(None, target_date, target_date, None)
            cursor.execute(f"SELECT COUNT(*) FROM businesses{today_where_clause}", today_params)
            today_approvals = cursor.fetchone()[0]
            
            # 2. Status distribution (파이 차트용 데이터, infer_update_type 기준)
            status_query = f"SELECT COALESCE(infer_update_type, 'null') as name, COUNT(*) as value FROM businesses{where_clause} GROUP BY name"
            cursor.execute(status_query, params)
            status_distribution = [{"name": row[0], "value": row[1]} for row in cursor.fetchall()]
            
            # 3. Trend chart
            trend_where = where_clause + (" AND " if where_clause else " WHERE ") + "last_event_date IS NOT NULL AND last_event_date != ''"
            trend_query = f"SELECT substr(last_event_date, 1, 10) as date, COUNT(*) as count FROM businesses{trend_where} GROUP BY date ORDER BY date ASC"
            cursor.execute(trend_query, params)
            
            db_trend_results = {row[0].replace('-', ''): row[1] for row in cursor.fetchall()}
            
            trend_chart = []
            if start_date and end_date:
                from datetime import datetime, timedelta
                try:
                    start_dt = datetime.strptime(start_date.replace('-', ''), '%Y%m%d')
                    end_dt = datetime.strptime(end_date.replace('-', ''), '%Y%m%d')
                    
                    if (end_dt - start_dt).days <= 365:
                        current_dt = start_dt
                        while current_dt <= end_dt:
                            date_str = current_dt.strftime('%Y%m%d')
                            trend_chart.append({
                                "date": date_str,
                                "count": db_trend_results.get(date_str, 0)
                            })
                            current_dt += timedelta(days=1)
                    else:
                        trend_chart = [{"date": k, "count": v} for k, v in db_trend_results.items()]
                except ValueError:
                    trend_chart = [{"date": k, "count": v} for k, v in db_trend_results.items()]
            else:
                trend_chart = [{"date": k, "count": v} for k, v in db_trend_results.items()]
            
            return total_approvals, today_approvals, status_distribution, trend_chart

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

    def insert_business(self, record: dict, conn=None):
        query = '''
            INSERT INTO businesses 
            (license_no, business_name, address, representative_name, business_status, license_date, phone_number, industry_type, last_event_date, is_new, update_type, prev_business_status, prev_representative_name, prev_business_name, infer_update_type, last_event_time, license_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            record["license_no"], record["business_name"], record["address"], 
            record["representative_name"], record["business_status"], 
            record["license_date"], record["phone_number"], record.get("industry_type"), record["last_event_date"],
            record.get("update_type"), record.get("prev_business_status"), 
            record.get("prev_representative_name"), record.get("prev_business_name"), record.get("infer_update_type"),
            record.get("last_event_time"), record.get("license_time")
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
                infer_update_type = ?,
                last_event_date = ?, last_event_time = ?, license_time = ?,
                updated_at = ?, is_new = 1
            WHERE license_no = ?
        '''
        params = (
            updates["business_name"], updates["address"], updates["representative_name"], 
            updates["business_status"], updates["phone_number"], updates.get("industry_type"),
            updates["representative_history"], updates["licensing_history"],
            updates.get("update_type"), updates.get("prev_business_status"), updates.get("prev_representative_name"), updates.get("prev_business_name"),
            updates.get("infer_update_type"),
            updates["last_event_date"], updates.get("last_event_time"), updates.get("license_time"),
            updates["updated_at"], license_no
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
