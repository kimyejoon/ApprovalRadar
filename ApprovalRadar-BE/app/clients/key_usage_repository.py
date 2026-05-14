"""
API 키 사용량 DB upsert 전담 모듈.
foodsafety_api.py에서 분리된 책임 단위입니다.
"""


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


def increment(masked: str, today: str) -> None:
    """일반 호출: 카운트 +1"""
    _upsert(masked, today)


def mark_exhausted(masked: str, today: str) -> None:
    """키 소진 마크: call_count=1000, exhausted=1"""
    _upsert(masked, today, exhausted=True)


def reset(masked: str, today: str) -> None:
    """키 초기화: call_count=0, exhausted=0"""
    _upsert(masked, today, reset=True)
