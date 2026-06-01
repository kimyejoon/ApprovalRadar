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
    
    # 신규등록 탭 단독 조회 시 특별 처리
    is_only_new_reg = (
        infer_update_type 
        and len(infer_update_type) == 1 
        and infer_update_type[0] == '신규등록'
    )
    
    if is_only_new_reg:
        conds = []
        
        # 조건 A: 태그가 '신규등록'이고, last_event_date가 범위 내인 경우
        cond_a = [
            "EXISTS (SELECT 1 FROM businesses b2 WHERE b2.license_no = businesses.license_no AND b2.last_event_date = businesses.last_event_date AND b2.infer_update_type = '신규등록')"
        ]
        if start_date:
            cond_a.append("last_event_date >= ?")
            params.append(start_date)
        if end_date:
            cond_a.append("last_event_date <= ?")
            params.append(end_date)
        conds.append(f"({' AND '.join(cond_a)})")
        
        # 조건 B: license_date가 유효하고, license_date가 범위 내인 경우 (신규등록 태그가 없어도 표시 가능)
        # 단, start_date 또는 end_date가 존재할 때만 적용하여 날짜 필터 해제 시 전체 데이터 매칭을 방지합니다.
        if start_date or end_date:
            cond_b = [
                "(license_date IS NOT NULL AND license_date != '' AND license_date != '미색인')"
            ]
            if start_date:
                cond_b.append("license_date >= ?")
                params.append(start_date)
            if end_date:
                cond_b.append("license_date <= ?")
                params.append(end_date)
            conds.append(f"({' AND '.join(cond_b)})")
        
        query_conditions.append(f"({' OR '.join(conds)})")
    else:
        # 일반 처리
        if infer_update_type:
            placeholders = ', '.join(['?'] * len(infer_update_type))
            query_conditions.append(
                f"EXISTS ("
                f"SELECT 1 FROM businesses b2 "
                f"WHERE b2.license_no = businesses.license_no "
                f"AND b2.last_event_date = businesses.last_event_date "
                f"AND b2.infer_update_type IN ({placeholders})"
                f")"
            )
            params.extend(infer_update_type)
            
        if start_date:
            query_conditions.append("last_event_date >= ?")
            params.append(start_date)
            
        if end_date:
            query_conditions.append("last_event_date <= ?")
            params.append(end_date)

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
