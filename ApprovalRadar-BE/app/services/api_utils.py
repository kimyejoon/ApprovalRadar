import asyncio
import random
from app.core.config import settings

async def fetch_page(api_client, service_id: str, start: int, end: int) -> list:
    """
    [start, end] 범위의 레코드를 비동기 조회하여 row 리스트를 반환합니다.
    bulk 응답 지연을 고려해 30초 timeout 사용.
    - INFO-000: 정상 데이터 리스트 반환
    - INFO-200: 빈 페이지(데이터 없음) → [] 반환
    - 기타 오류: [] 반환
    WAF 차단 방지를 위해 호출 후 Jitter(무작위 지연) 적용.
    """
    res = await api_client.fetch_data(service_id, start, end, timeout=30)
    # WAF 차단 방지: API 호출 직후 무작위 지연
    await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
    if not res or service_id not in res:
        return []
    block = res[service_id]
    code = block['RESULT']['CODE']
    if code == "INFO-000":
        return block.get('row', [])
    return []
