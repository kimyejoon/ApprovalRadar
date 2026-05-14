"""
피벗 샘플링 및 갱신 전담 모듈.
diff_crawler.py에서 분리된 책임 단위입니다.
"""
import asyncio
import random
from app.core.config import settings
from app.core.logger import logger

PAGE_SIZE = 1000  # diff_crawler.py와 동일한 상수


async def sample_check(pivots: dict, api_client, service_id: str, sample_ratio: float = 0.2) -> bool:
    """
    저장된 피벗 중 일부를 무작위로 샘플링하여 API 현재 응답과 비교합니다.
    Delete가 은폐(Insert+Delete 동시 발생)된 경우 피벗의 LCNS_NO가 바뀌어 있습니다.
    ✅ Boundary 양방향 보완: LCNS_NO(첫 번째) + LAST_LCNS_NO(마지막) 모두 검증
    Returns: True = 불일치 감지(Delete 의심), False = 정상
    """
    if not pivots:
        return False

    pivot_items = list(pivots.items())
    sample_size = max(1, int(len(pivot_items) * sample_ratio))
    sampled = random.sample(pivot_items, min(sample_size, len(pivot_items)))

    for idx_str, pivot_data in sampled:
        idx = int(idx_str)
        # pivot_data는 dict(신규) 또는 str(레거시) 형태일 수 있음
        if isinstance(pivot_data, dict):
            expected_lcns_no = pivot_data.get("LCNS_NO", "")
            expected_last_lcns_no = pivot_data.get("LAST_LCNS_NO", "")  # 신규 Boundary 필드
        else:
            expected_lcns_no = str(pivot_data)  # 레거시 문자열 포맷 호환
            expected_last_lcns_no = ""
        try:
            # 첫 번째 행 검증
            res = await api_client.fetch_data(service_id, idx, idx)
            # WAF 차단 방지: 피벗 샘플링 API 호출 직후 Jitter 적용
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
            items = res.get(service_id, {}).get("row", [])
            if not items:
                continue
            actual_lcns_no = items[0].get("LCNS_NO", "")
            if actual_lcns_no != expected_lcns_no:
                logger.warning(
                    f"[{service_id}][피벗 샘플링] idx={idx} 첫번째 불일치! "
                    f"저장값(LCNS_NO)={expected_lcns_no}, 현재값={actual_lcns_no}"
                )
                return True

            # ✅ 마지막 행 검증 (LAST_LCNS_NO 저장된 경우만)
            if expected_last_lcns_no:
                last_res = await api_client.fetch_data(service_id, idx + PAGE_SIZE - 1, idx + PAGE_SIZE - 1)
                # WAF 차단 방지: 피벗 샘플링 마지막 행 API 호출 직후 Jitter 적용
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
                last_items = last_res.get(service_id, {}).get("row", [])
                if last_items:
                    actual_last_lcns_no = last_items[0].get("LCNS_NO", "")
                    if actual_last_lcns_no != expected_last_lcns_no:
                        logger.warning(
                            f"[{service_id}][피벗 샘플링] idx={idx} 마지막 행 불일치! "
                            f"저장값(LAST_LCNS_NO)={expected_last_lcns_no}, 현재값={actual_last_lcns_no}"
                        )
                        return True

        except Exception as e:
            logger.debug(f"[{service_id}][피벗 샘플링] idx={idx} 조회 실패: {e}")
            continue
    return False
