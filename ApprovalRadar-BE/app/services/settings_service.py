import datetime
from database import get_db
from app.core.logger import logger

def _reload_settings_keys():
    """DB에서 활성 키를 다시 로드하여 settings.API_KEYS를 갱신합니다 (무중단)."""
    from app.core.config import settings
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT key_value FROM api_keys WHERE is_active = 1 ORDER BY id"
            ).fetchall()
            settings.API_KEYS = [row["key_value"] for row in rows if row["key_value"]]
        logger.info(f"[settings] API 키 갱신 완료: {len(settings.API_KEYS)}개 활성 키 로드됨.")
    except Exception as e:
        logger.error(f"[settings] API 키 갱신 중 오류: {e}")


def _recalculate_optimal_settings():
    """API 키 수 변경에 맞춰 Rolling Scan 페이지 수와 크롤링 주기를 자동 최적화합니다."""
    from app.core.config import settings, compute_optimal_defaults, _get_service_page_counts

    num_keys = len(settings.API_KEYS)
    if num_keys == 0:
        return

    try:
        page_counts = _get_service_page_counts()
        result = compute_optimal_defaults(
            num_api_keys=num_keys,
            services_page_counts=page_counts,
            tail_ping_calls_per_cycle=len(settings.SERVICES) * 2,
        )
        if not result:
            return

        old_pages = settings.ROLLING_SCAN_PAGES_PER_CYCLE
        new_pages = result["total_pages_per_cycle"]
        old_interval = settings.SCRAPER_INTERVAL_MINUTES
        new_interval = result["interval_minutes"]

        changes = []
        if old_pages != new_pages:
            settings.ROLLING_SCAN_PAGES_PER_CYCLE = new_pages
            changes.append(f"Rolling {old_pages}→{new_pages}p/주기")

        if old_interval != new_interval:
            settings.SCRAPER_INTERVAL_MINUTES = new_interval
            try:
                from app.core.scheduler import reschedule_scraper_job
                reschedule_scraper_job(new_interval)
            except Exception:
                pass
            changes.append(f"주기 {old_interval}→{new_interval}분")

        if changes:
            max_rot = max(result["rotation_hours"].values())
            logger.info(
                f"[자동 최적화] 키 {num_keys}개 기준: {', '.join(changes)}, "
                f"1회전 ~{max_rot}h, API {result['budget_usage_pct']}%"
            )
    except Exception as e:
        logger.warning(f"[자동 최적화] 계산 실패 (무시): {e}")


def validate_and_recover_key(key_value: str) -> bool:
    """새 키가 추가되었을 때, API 소진 플래그 해제 및 크롤링 자동 재개를 처리합니다."""
    from app.clients.foodsafety_api import ApiClient
    from app.core.config import settings as _settings

    if not ApiClient.is_exhausted():
        return False

    # 새 키가 실제로 유효한지 API 찔러봄 (동기식 HTTP request)
    import httpx

    def _mask_key(key: str) -> str:
        return f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"

    url = f"{_settings.BASE_URL}/{key_value}/{_settings.SERVICE_ID}/{_settings.DATA_TYPE}/1/1"
    try:
        res = httpx.get(url, timeout=7).json()
        if _settings.SERVICE_ID in res:
            code = res[_settings.SERVICE_ID]['RESULT']['CODE']
            if code == "INFO-000":
                masked_new = _mask_key(key_value)
                ApiClient.recover_exhaustion({masked_new})
                logger.info(f"[settings] 새 키 {masked_new} 검증 통과 → 소진 플래그 해제, 크롤링 재개 예약")

                # 즉시 1회 스크래퍼 실행 (비동기 safe)
                from app.core.scheduler import trigger_immediate_scrape
                trigger_immediate_scrape()
                return True
    except Exception as e:
        logger.warning(f"[settings] 새 키 검증 통과 실패 중 오류: {e}")

    logger.warning(f"[settings] 새 키 검증 실패 (비활성/소진 키). 소진 상태 유지.")
    return False
