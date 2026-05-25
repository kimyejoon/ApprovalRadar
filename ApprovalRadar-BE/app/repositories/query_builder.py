from typing import Optional, List, Tuple, Any

def build_business_where_clause(
    search: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    regions: Optional[List[str]],
    infer_update_type: Optional[List[str]] = None,
    industry_type: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None
) -> Tuple[str, List[Any]]:
    query_conditions = []
    params = []
    
    if infer_update_type:
        placeholders = ', '.join(['?'] * len(infer_update_type))
        # 같은 날 같은 업소에 여러 변경 유형이 있을 경우,
        # 하나라도 매칭되면 해당 날짜 레코드 전체를 가져옴 (프론트 그룹핑용)
        query_conditions.append(
            f"EXISTS ("
            f"SELECT 1 FROM businesses b2 "
            f"WHERE b2.license_no = businesses.license_no "
            f"AND b2.last_event_date = businesses.last_event_date "
            f"AND b2.infer_update_type IN ({placeholders})"
            f")"
        )
        params.extend(infer_update_type)
        
    if industry_type:
        placeholders = ', '.join(['?'] * len(industry_type))
        query_conditions.append(f"industry_type IN ({placeholders})")
        params.extend(industry_type)
        
    if exclude_keywords:
        for kw in exclude_keywords:
            query_conditions.append("business_name NOT LIKE ?")
            params.append(f"%{kw}%")
        
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
            # Map standard region names to database address start patterns to ensure
            # special provinces (like 강원특별자치도, 전북특별자치도) are matched and false positives are avoided.
            prefixes = []
            if r == '강원도':
                prefixes = ['강원도%', '강원특별%']
            elif r == '전라북도':
                prefixes = ['전라북도%', '전북%']
            elif r == '제주특별자치도':
                prefixes = ['제주%']
            elif r == '세종특별자치시':
                prefixes = ['세종%']
            elif r == '서울특별시':
                prefixes = ['서울%']
            elif r == '인천광역시':
                prefixes = ['인천%']
            elif r == '경기도':
                prefixes = ['경기%']
            elif r == '부산광역시':
                prefixes = ['부산%']
            elif r == '대구광역시':
                prefixes = ['대구%']
            elif r == '광주광역시':
                prefixes = ['광주%']
            elif r == '대전광역시':
                prefixes = ['대전%']
            elif r == '울산광역시':
                prefixes = ['울산%']
            elif r == '충청북도':
                prefixes = ['충청북도%', '충북%']
            elif r == '충청남도':
                prefixes = ['충청남도%', '충남%']
            elif r == '전라남도':
                prefixes = ['전라남도%', '전남%']
            elif r == '경상북도':
                prefixes = ['경상북도%', '경북%']
            elif r == '경상남도':
                prefixes = ['경상남도%', '경남%']
            else:
                prefixes = [f"{r}%"]
            
            for p in prefixes:
                region_conditions.append("address LIKE ?")
                params.append(p)
                
        if region_conditions:
            query_conditions.append(f"({' OR '.join(region_conditions)})")
    
    where_clause = ""
    if query_conditions:
        where_clause = " WHERE " + " AND ".join(query_conditions)
        
    return where_clause, params
