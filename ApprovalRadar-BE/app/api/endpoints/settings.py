import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
from typing import Optional, List

from database import get_db
from app.core.logger import logger

router = APIRouter()


# ─── 응답 스키마 ─────────────────────────────────────────────────────────────

class ApiKeyItem(BaseModel):
    id: int
    key_masked: str          # 마스킹된 키 (표시용)
    memo: Optional[str] = None
    is_active: bool
    created_at: str
    call_count_today: int = 0
    is_exhausted: bool = False
    crawl_resumed: bool = False  # 새 키 추가로 크롤링이 재개됐으면 True


class ApiKeyListResponse(BaseModel):
    total: int
    keys: List[ApiKeyItem]


class ApiKeyCreateRequest(BaseModel):
    key_value: str
    memo: Optional[str] = None


class ApiKeyUpdateRequest(BaseModel):
    memo: Optional[str] = None
    is_active: Optional[bool] = None


# ─── 내부 유틸 ───────────────────────────────────────────────────────────────

def _mask_key(key: str) -> str:
    return f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"


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


# ─── 키 목록 조회 ────────────────────────────────────────────────────────────

@router.get(
    "/api-keys",
    response_model=ApiKeyListResponse,
    summary="API 키 목록 조회",
    description="DB에 등록된 모든 API 키와 오늘 사용량을 반환합니다. 키는 마스킹 처리됩니다.",
)
async def list_api_keys():
    today = datetime.date.today().isoformat()
    items: List[ApiKeyItem] = []

    try:
        with get_db() as conn:
            keys = conn.execute(
                "SELECT id, key_value, memo, is_active, created_at FROM api_keys ORDER BY id"
            ).fetchall()

            usage_rows = conn.execute(
                "SELECT key_masked, call_count, exhausted FROM api_key_usage WHERE usage_date = ?",
                (today,)
            ).fetchall()
            usage_map = {r["key_masked"]: r for r in usage_rows}

        for key_row in keys:
            masked = _mask_key(key_row["key_value"])
            usage = usage_map.get(masked)
            items.append(ApiKeyItem(
                id=key_row["id"],
                key_masked=masked,
                memo=key_row["memo"],
                is_active=bool(key_row["is_active"]),
                created_at=key_row["created_at"] or "",
                call_count_today=usage["call_count"] if usage else 0,
                is_exhausted=bool(usage["exhausted"]) if usage else False,
            ))
    except Exception as e:
        logger.error(f"[settings] 키 목록 조회 오류: {e}")
        raise HTTPException(status_code=500, detail="API 키 목록 조회 실패")

    return ApiKeyListResponse(total=len(items), keys=items)


# ─── 키 추가 ─────────────────────────────────────────────────────────────────

@router.post(
    "/api-keys",
    response_model=ApiKeyItem,
    summary="API 키 추가",
    description="새 API 키를 DB에 등록합니다. 등록 후 서버 재시작 없이 즉시 적용됩니다.",
)
async def create_api_key(body: ApiKeyCreateRequest):
    key_value = body.key_value.strip()
    if not key_value:
        raise HTTPException(status_code=400, detail="키 값이 비어있습니다.")

    try:
        with get_db() as conn:
            try:
                conn.execute(
                    "INSERT INTO api_keys (key_value, memo, is_active) VALUES (?, ?, 1)",
                    (key_value, body.memo)
                )
                conn.commit()
            except Exception:
                raise HTTPException(status_code=409, detail="이미 등록된 키입니다.")

            row = conn.execute(
                "SELECT id, key_value, memo, is_active, created_at FROM api_keys WHERE key_value = ?",
                (key_value,)
            ).fetchone()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] 키 추가 오류: {e}")
        raise HTTPException(status_code=500, detail="API 키 추가 실패")

    _reload_settings_keys()
    _recalculate_optimal_settings()
    logger.info(f"[settings] API 키 추가: {_mask_key(key_value)} | 메모: {body.memo}")

    # ── 소진 상태 검증 및 크롤링 자동 재개 ──────────────────────────────────
    crawl_resumed = False
    from app.clients.foodsafety_api import ApiClient
    from app.core.config import settings as _settings

    if ApiClient.is_exhausted():
        # 새 키가 실제로 유효한지 API 찔러봄 (비동기 → asyncio.run)
        import asyncio
        # pyrefly: ignore [missing-import]
        import httpx

        def _validate_key(k: str) -> bool:
            """새 키에 대해 실제 API 1건 요청으로 활성 여부 확인."""
            url = f"{_settings.BASE_URL}/{k}/{_settings.SERVICE_ID}/{_settings.DATA_TYPE}/1/1"
            try:
                res = httpx.get(url, timeout=7).json()
                if _settings.SERVICE_ID in res:
                    code = res[_settings.SERVICE_ID]['RESULT']['CODE']
                    return code == "INFO-000"
            except Exception:
                pass
            return False

        if _validate_key(key_value):
            masked_new = _mask_key(key_value)
            ApiClient.recover_exhaustion({masked_new})
            logger.info(f"[settings] 새 키 {masked_new} 검증 통과 → 소진 플래그 해제, 크롤링 재개 예약")

            # 즉시 1회 스크래퍼 실행 (비동기 safe: 별도 APScheduler 잡으로 위임)
            from app.core.scheduler import trigger_immediate_scrape
            trigger_immediate_scrape()
            crawl_resumed = True
        else:
            logger.warning(f"[settings] 새 키 {_mask_key(key_value)} 검증 실패 (비활성/소진 키). 소진 상태 유지.")

    return ApiKeyItem(
        id=row["id"],
        key_masked=_mask_key(row["key_value"]),
        memo=row["memo"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"] or "",
        call_count_today=0,
        is_exhausted=False,
        crawl_resumed=crawl_resumed,
    )


# ─── 키 수정 (메모 / 활성화 토글) ────────────────────────────────────────────

@router.patch(
    "/api-keys/{key_id}",
    response_model=ApiKeyItem,
    summary="API 키 수정",
    description="메모 또는 활성화 상태를 수정합니다.",
)
async def update_api_key(key_id: int, body: ApiKeyUpdateRequest):
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, key_value, memo, is_active, created_at FROM api_keys WHERE id = ?",
                (key_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")

            new_memo = body.memo if body.memo is not None else row["memo"]
            new_active = int(body.is_active) if body.is_active is not None else row["is_active"]

            conn.execute(
                "UPDATE api_keys SET memo = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_memo, new_active, key_id)
            )
            conn.commit()

            today = datetime.date.today().isoformat()
            masked = _mask_key(row["key_value"])
            usage = conn.execute(
                "SELECT call_count, exhausted FROM api_key_usage WHERE key_masked = ? AND usage_date = ?",
                (masked, today)
            ).fetchone()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] 키 수정 오류: {e}")
        raise HTTPException(status_code=500, detail="API 키 수정 실패")

    _reload_settings_keys()
    _recalculate_optimal_settings()
    logger.info(f"[settings] API 키 수정: {_mask_key(row['key_value'])} | active={new_active}")

    return ApiKeyItem(
        id=key_id,
        key_masked=_mask_key(row["key_value"]),
        memo=new_memo,
        is_active=bool(new_active),
        created_at=row["created_at"] or "",
        call_count_today=usage["call_count"] if usage else 0,
        is_exhausted=bool(usage["exhausted"]) if usage else False,
    )


# ─── 키 삭제 ─────────────────────────────────────────────────────────────────

@router.delete(
    "/api-keys/{key_id}",
    summary="API 키 삭제",
    description="DB에서 API 키를 영구 삭제합니다.",
)
async def delete_api_key(key_id: int):
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT key_value FROM api_keys WHERE id = ?", (key_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")

            masked = _mask_key(row["key_value"])
            conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] 키 삭제 오류: {e}")
        raise HTTPException(status_code=500, detail="API 키 삭제 실패")

    _reload_settings_keys()
    _recalculate_optimal_settings()
    logger.info(f"[settings] API 키 삭제: {masked}")
    return {"status": "ok", "deleted_key": masked}

# ─── 크롤링 주기 설정 ─────────────────────────────────────────────────────────

class CrawlIntervalResponse(BaseModel):
    interval_minutes: int

class CrawlIntervalUpdateRequest(BaseModel):
    interval_minutes: int

@router.get(
    "/crawl-interval",
    response_model=CrawlIntervalResponse,
    summary="현재 크롤링 주기 조회",
)
async def get_crawl_interval():
    from app.core.config import settings as _s
    return CrawlIntervalResponse(interval_minutes=_s.SCRAPER_INTERVAL_MINUTES)


@router.put(
    "/crawl-interval",
    response_model=CrawlIntervalResponse,
    summary="크롤링 주기 변경",
    description="크롤링 주기를 변경합니다. 5~120분 범위에서 설정 가능. 서버 재시작 없이 즉시 반영됩니다.",
)
async def update_crawl_interval(body: CrawlIntervalUpdateRequest):
    if not (5 <= body.interval_minutes <= 120):
        raise HTTPException(status_code=422, detail="크롤링 주기는 5~120분 범위여야 합니다.")
    try:
        from app.core.config import settings as _s
        from app.core.scheduler import reschedule_scraper_job
        _s.SCRAPER_INTERVAL_MINUTES = body.interval_minutes
        reschedule_scraper_job(body.interval_minutes)
        logger.info(f"[settings] 크롤링 주기 변경: {body.interval_minutes}분")
    except Exception as e:
        logger.error(f"[settings] 크롤링 주기 변경 오류: {e}")
        raise HTTPException(status_code=500, detail="크롤링 주기 변경 실패")
    return CrawlIntervalResponse(interval_minutes=body.interval_minutes)


# ─── Rolling Scan 스캔 속도 설정 ─────────────────────────────────────────────

class RollingScanRateResponse(BaseModel):
    pages_per_cycle: int

class RollingScanRateUpdateRequest(BaseModel):
    pages_per_cycle: int

@router.get(
    "/rolling-scan-rate",
    response_model=RollingScanRateResponse,
    summary="Rolling Scan 주기당 스캔 페이지 수 조회",
)
async def get_rolling_scan_rate():
    from app.core.config import settings as _s
    return RollingScanRateResponse(pages_per_cycle=_s.ROLLING_SCAN_PAGES_PER_CYCLE)


@router.put(
    "/rolling-scan-rate",
    response_model=RollingScanRateResponse,
    summary="Rolling Scan 주기당 스캔 페이지 수 변경",
    description="주기당 스캔할 페이지 수를 변경합니다. 10~200 범위에서 설정 가능. 서버 재시작 없이 즉시 반영됩니다.",
)
async def update_rolling_scan_rate(body: RollingScanRateUpdateRequest):
    if not (10 <= body.pages_per_cycle <= 200):
        raise HTTPException(status_code=422, detail="스캔 페이지 수는 10~200 범위여야 합니다.")
    try:
        from app.core.config import settings as _s
        _s.ROLLING_SCAN_PAGES_PER_CYCLE = body.pages_per_cycle
        logger.info(f"[settings] Rolling Scan 스캔 속도 변경: {body.pages_per_cycle}페이지/주기")
    except Exception as e:
        logger.error(f"[settings] Rolling Scan 스캔 속도 변경 오류: {e}")
        raise HTTPException(status_code=500, detail="Rolling Scan 설정 변경 실패")
    return RollingScanRateResponse(pages_per_cycle=body.pages_per_cycle)
