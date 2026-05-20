from typing import Optional, List, Tuple, Any

def build_business_where_clause(
    search: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    regions: Optional[List[str]],
    infer_update_type: Optional[List[str]] = None,
    industry_type: Optional[List[str]] = None
) -> Tuple[str, List[Any]]:
    query_conditions = []
    params = []
    
    if infer_update_type:
        placeholders = ', '.join(['?'] * len(infer_update_type))
        query_conditions.append(f"infer_update_type IN ({placeholders})")
        params.extend(infer_update_type)
        
    if industry_type:
        placeholders = ', '.join(['?'] * len(industry_type))
        query_conditions.append(f"industry_type IN ({placeholders})")
        params.extend(industry_type)
        
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
