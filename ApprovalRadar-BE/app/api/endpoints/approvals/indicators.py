from fastapi import APIRouter, HTTPException, Depends
from app.repositories.business_repository import BusinessRepository
from app.schemas.approvals import IndicatorsResponse
from app.core.logger import logger
from cachetools import TTLCache

router = APIRouter()

# maxsize=64: 날짜 기반 key 수 상한 (1년 운영해도 365개 이하)
# ttl=600: 기존 CACHE_TTL(10분)과 동일, 만료된 항목은 자동 제거
_INDICATORS_CACHE: TTLCache = TTLCache(maxsize=64, ttl=600)

def get_business_repo() -> BusinessRepository:
    return BusinessRepository()

@router.get("/indicators", response_model=IndicatorsResponse)
def get_approval_indicators(
    repo: BusinessRepository = Depends(get_business_repo)
):
    try:
        from datetime import datetime, timedelta
        
        # 항상 최근 30일로 고정
        today = datetime.now()
        start_date = (today - timedelta(days=29)).strftime('%Y%m%d')
        end_date = today.strftime('%Y%m%d')

        cache_key = f"indicators_fixed_30d_{start_date}_{end_date}"
        cached = _INDICATORS_CACHE.get(cache_key)
        
        if cached is not None:
            return cached
            
        total_approvals, monthly_approvals, today_approvals, status_distribution, trend_chart = repo.get_indicators(start_date, end_date)
            
        response_data = {
            "status": "success",
            "data": {
                "total_approvals": total_approvals,
                "monthly_approvals": monthly_approvals,
                "today_approvals": today_approvals,
                "status_distribution": status_distribution,
                "trend_chart": trend_chart
            }
        }
        
        _INDICATORS_CACHE[cache_key] = response_data
        return response_data
    except Exception as e:
        logger.error(f"Database error in get_approval_indicators: {e}")
        raise HTTPException(status_code=500, detail="내부 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
