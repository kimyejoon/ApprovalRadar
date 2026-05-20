from datetime import datetime

def parse_scan_time(value: str) -> datetime | None:
    """scan_times 값을 datetime으로 파싱. ISO/HH:MM:SS 모두 지원."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        pass
    # 레거시 HH:MM:SS → 오늘 날짜 + 시간으로 해석
    try:
        t = datetime.strptime(value, "%H:%M:%S").time()
        return datetime.combine(datetime.now().date(), t)
    except (ValueError, TypeError):
        return None

def migrate_scan_times(scan_times: dict) -> int:
    """HH:MM:SS 레거시 값을 ISO datetime으로 일괄 변환."""
    migrated = 0
    today = datetime.now().date()
    for k, v in list(scan_times.items()):
        if v and 'T' not in str(v):
            try:
                t = datetime.strptime(v, "%H:%M:%S").time()
                scan_times[k] = datetime.combine(today, t).isoformat()
                migrated += 1
            except (ValueError, TypeError):
                del scan_times[k]
                migrated += 1
    return migrated

def select_oldest_pages(scan_times: dict, total_pages: int, count: int, page_size: int, min_age_sec: int = 3600) -> list:
    """
    경과 시간 기준으로 가장 오래된 페이지 count개 선택.
    미스캔 페이지(scan_times에 없는)가 최우선.
    """
    now = datetime.now()
    candidates = []
    for page_idx in range(total_pages):
        page_start = page_idx * page_size + 1
        key = str(page_start)
        last_scan = scan_times.get(key)
        if last_scan is None:
            age = float('inf')
        else:
            parsed = parse_scan_time(last_scan)
            age = (now - parsed).total_seconds() if parsed else float('inf')
        if age >= min_age_sec:
            candidates.append((page_start, age))

    candidates.sort(key=lambda x: -x[1])
    return [c[0] for c in candidates[:count]]

def get_page_age(scan_times: dict, page_start: int) -> float:
    """페이지의 연식(시간)을 반환."""
    key = str(page_start)
    last_scan = scan_times.get(key)
    if last_scan is None:
        return 999.9
    parsed = parse_scan_time(last_scan)
    if parsed is None:
        return 999.9
    return (datetime.now() - parsed).total_seconds() / 3600

def extract_new_rows(current_items: list, fingerprints: dict, page_start: int) -> list:
    """
    fingerprint 불일치 페이지에서 신규 삽입 레코드를 추출합니다.
    """
    return current_items

def build_fingerprints_from_bootstrap(api_client, service_id: str, total_count: int) -> dict:
    """Bootstrap 호환용 — 실제 fingerprint는 scan_cycle 중 점진적으로 채워짐."""
    return {}
