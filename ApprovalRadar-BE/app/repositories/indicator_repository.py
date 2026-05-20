from typing import Optional, List, Dict, Any, Tuple
from database import get_db
from app.repositories.query_builder import build_business_where_clause

class IndicatorRepository:
    def get_indicators(self, start_date: Optional[str], end_date: Optional[str]) -> Tuple[int, int, int, List[Dict[str, Any]], List[Dict[str, Any]]]:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # 1. Total approvals (전체 기간, 필터 없음)
            cursor.execute("SELECT COUNT(*) FROM businesses")
            total_approvals = cursor.fetchone()[0]

            # 1.2 Monthly approvals (파라미터로 넘어온 start_date ~ end_date 기준, 보통 30일)
            where_clause, params = build_business_where_clause(None, start_date, end_date, None, None, None)
            cursor.execute(f"SELECT COUNT(*) FROM businesses{where_clause}", params)
            monthly_approvals = cursor.fetchone()[0]

            # 1.5 Today approvals (Target Day Only)
            target_date = end_date
            if not target_date:
                from datetime import datetime
                target_date = datetime.now().strftime('%Y%m%d')
                
            today_where_clause, today_params = build_business_where_clause(None, target_date, target_date, None, None, None)
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
            
            return total_approvals, monthly_approvals, today_approvals, status_distribution, trend_chart
