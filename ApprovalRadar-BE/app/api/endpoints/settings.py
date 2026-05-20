import datetime
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
from typing import Optional, List

from app.core.logger import logger
from app.repositories.api_key_repository import ApiKeyRepository
from app.services.settings_service import (
    _reload_settings_keys,
    _recalculate_optimal_settings,
    validate_and_recover_key,
)

router = APIRouter()
repo = ApiKeyRepository()


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
        keys = repo.get_all_keys()
        usage_rows = repo.get_key_usages(today)
        usage_map = {r["key_masked"]: r for r in usage_rows}

        for key_row in keys:
            masked = repo.mask_key(key_row["key_value"])
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
        try:
            repo.insert_key(key_value, body.memo)
        except Exception:
            raise HTTPException(status_code=409, detail="이미 등록된 키입니다.")

        row = repo.get_key_by_value(key_value)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] 키 추가 오류: {e}")
        raise HTTPException(status_code=500, detail="API 키 추가 실패")

    _reload_settings_keys()
    _recalculate_optimal_settings()
    logger.info(f"[settings] API 키 추가: {repo.mask_key(key_value)} | 메모: {body.memo}")

    # 소진 검증 및 크롤링 복구 비즈니스 로직 위임
    crawl_resumed = validate_and_recover_key(key_value)

    return ApiKeyItem(
        id=row["id"],
        key_masked=repo.mask_key(row["key_value"]),
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
        row = repo.get_key_by_id(key_id)
        if not row:
            raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")

        new_memo = body.memo if body.memo is not None else row["memo"]
        new_active = int(body.is_active) if body.is_active is not None else row["is_active"]

        repo.update_key(key_id, new_memo, new_active)

        today = datetime.date.today().isoformat()
        masked = repo.mask_key(row["key_value"])
        usage = repo.get_usage_by_masked_and_date(masked, today)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] 키 수정 오류: {e}")
        raise HTTPException(status_code=500, detail="API 키 수정 실패")

    _reload_settings_keys()
    _recalculate_optimal_settings()
    logger.info(f"[settings] API 키 수정: {repo.mask_key(row['key_value'])} | active={new_active}")

    return ApiKeyItem(
        id=key_id,
        key_masked=repo.mask_key(row["key_value"]),
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
        row = repo.get_key_by_id(key_id)
        if not row:
            raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")

        masked = repo.mask_key(row["key_value"])
        repo.delete_key(key_id)
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

