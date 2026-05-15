"""
API 키 사용량 DB upsert 전담 모듈.
foodsafety_api.py에서 분리된 책임 단위입니다.
"""

# 서비스 ID → 사용자 친화적 이름 (로그 가독성용)
SERVICE_NAME_MAP: dict[str, str] = {
    "I2859": "식품업소 인허가변경",
    "I2861": "음식점업소 인허가변경",
    "I2500": "인허가 업소 정보",
}


def _upsert(masked: str, today: str, *, exhausted: bool = False, reset: bool = False) -> None:
    """api_key_usage 테이블에 사용량을 upsert합니다. 실패해도 크롤링에 영향 없음."""
    try:
        from database import get_db
        with get_db() as conn:
            if exhausted:
                conn.execute(
                    '''INSERT INTO api_key_usage (key_masked, usage_date, call_count, exhausted, last_updated)
                       VALUES (?, ?, 1000, 1, CURRENT_TIMESTAMP)
                       ON CONFLICT(key_masked, usage_date)
                       DO UPDATE SET call_count=1000, exhausted=1, last_updated=CURRENT_TIMESTAMP''',
                    (masked, today)
                )
            elif reset:
                conn.execute(
                    '''INSERT INTO api_key_usage (key_masked, usage_date, call_count, exhausted, last_updated)
                       VALUES (?, ?, 0, 0, CURRENT_TIMESTAMP)
                       ON CONFLICT(key_masked, usage_date)
                       DO UPDATE SET call_count=0, exhausted=0, last_updated=CURRENT_TIMESTAMP''',
                    (masked, today)
                )
            else:
                conn.execute(
                    '''INSERT INTO api_key_usage (key_masked, usage_date, call_count, last_updated)
                       VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                       ON CONFLICT(key_masked, usage_date)
                       DO UPDATE SET call_count = call_count + 1, last_updated = CURRENT_TIMESTAMP''',
                    (masked, today)
                )
            conn.commit()
    except Exception:
        pass  # 사용량 기록 실패는 크롤링에 영향 없음


def _upsert_by_service(masked: str, today: str, service_id: str) -> None:
    """api_key_usage_by_service 테이블에 서비스별 호출 카운트 +1 upsert."""
    if not service_id:
        return
    try:
        from database import get_db
        with get_db() as conn:
            conn.execute(
                '''INSERT INTO api_key_usage_by_service (key_masked, usage_date, service_id, call_count, last_updated)
                   VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT(key_masked, usage_date, service_id)
                   DO UPDATE SET call_count = call_count + 1, last_updated = CURRENT_TIMESTAMP''',
                (masked, today, service_id)
            )
            conn.commit()
    except Exception:
        pass


def increment(masked: str, today: str, service_id: str = "") -> None:
    """일반 호출: 키별 총 카운트 +1 및 서비스별 카운트 +1"""
    _upsert(masked, today)
    if service_id:
        _upsert_by_service(masked, today, service_id)


def get_today_count(masked: str, today: str) -> int:
    """오늘 해당 키의 총 호출 카운트를 반환합니다."""
    try:
        from database import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT call_count FROM api_key_usage WHERE key_masked = ? AND usage_date = ?",
                (masked, today)
            ).fetchone()
            return row["call_count"] if row else 0
    except Exception:
        return 0


def mark_exhausted(masked: str, today: str) -> None:
    """키 소진 마크: call_count=1000, exhausted=1"""
    _upsert(masked, today, exhausted=True)


def reset(masked: str, today: str) -> None:
    """키 초기화: call_count=0, exhausted=0"""
    _upsert(masked, today, reset=True)
