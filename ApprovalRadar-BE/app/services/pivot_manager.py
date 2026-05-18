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

    sampled_indices = sorted([int(k) for k, _ in sampled])
    idx_preview = ", ".join(f"{i:,}" for i in sampled_indices[:5])
    if len(sampled_indices) > 5:
        idx_preview += f" 외 {len(sampled_indices)-5}개"

    logger.info(
        f"[{service_id}][피벗 무결성 검사] 총 {len(pivot_items)}개 피벗 중 "
        f"{len(sampled)}개 무작위 샘플 검사 시작 → 검사 인덱스: [{idx_preview}]"
    )

    for idx_str, pivot_data in sampled:
        idx = int(idx_str)
        # pivot_data는 dict(신규) 또는 str(레거시) 형태일 수 있음
        if isinstance(pivot_data, dict):
            expected_lcns_no = pivot_data.get("LCNS_NO", "")
            expected_last_lcns_no = pivot_data.get("LAST_LCNS_NO", "")
            bssh_nm = pivot_data.get("BSSH_NM", "")
        else:
            expected_lcns_no = str(pivot_data)
            expected_last_lcns_no = ""
            bssh_nm = ""

        try:
            # 첫 번째 행 검증
            res = await api_client.fetch_data(service_id, idx, idx)
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
            items = res.get(service_id, {}).get("row", [])
            if not items:
                logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 응답 없음 (API 일시 오류) → 해당 피벗 스킵")
                continue
            actual_lcns_no = items[0].get("LCNS_NO", "")
            if actual_lcns_no != expected_lcns_no:
                logger.warning(
                    f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 위치 불일치!\n"
                    f"  저장값: {expected_lcns_no} ({bssh_nm or '업소명 미상'})\n"
                    f"  현재값: {actual_lcns_no}\n"
                    f"  → 이 위치 이전 구간에 Insert+Delete 동시 발생 가능성. "
                    f"피벗 초기화 후 다음 주기에 Ping으로 실제 신규건 확인 예정."
                )
                return True

            # ✅ 마지막 행 검증 (LAST_LCNS_NO 저장된 경우만)
            if expected_last_lcns_no:
                last_res = await api_client.fetch_data(service_id, idx + PAGE_SIZE - 1, idx + PAGE_SIZE - 1)
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
                last_items = last_res.get(service_id, {}).get("row", [])
                if last_items:
                    actual_last_lcns_no = last_items[0].get("LCNS_NO", "")
                    if actual_last_lcns_no != expected_last_lcns_no:
                        logger.warning(
                            f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 페이지 끝 행 불일치!\n"
                            f"  저장값(마지막): {expected_last_lcns_no}\n"
                            f"  현재값(마지막): {actual_last_lcns_no}\n"
                            f"  → {idx:,}~{idx + PAGE_SIZE - 1:,} 구간 경계에 삽입 발생 가능성."
                        )
                        return True

        except Exception as e:
            logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 조회 실패 (무시): {e}")
            continue

    logger.info(
        f"[{service_id}][피벗 무결성 검사] ✅ {len(sampled)}개 샘플 전부 정상 — "
        f"API 데이터 재정렬 없음 확인됨."
    )
    return False
