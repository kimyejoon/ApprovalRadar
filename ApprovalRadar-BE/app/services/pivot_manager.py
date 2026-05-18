"""
피벗 샘플링 및 갱신 전담 모듈.
diff_crawler.py에서 분리된 책임 단위입니다.
"""
import asyncio
import random
from app.core.config import settings
from app.core.logger import logger

PAGE_SIZE = 1000  # diff_crawler.py와 동일한 상수


async def sample_check(pivots: dict, api_client, service_id: str, sample_ratio: float = 0.2) -> tuple:
    """
    저장된 피벗 중 일부를 무작위 샘플링하여 API 현재 응답과 비교합니다.

    ✅ 강화된 진단: 불일치 감지 시 1,000건 윈도우 조회로 Shift 정확도 즉시 계산
    Returns: (changed: bool, shift_info: dict)
      shift_info keys:
        - first_mismatch_idx: int        (불일치 발견된 피벗 인덱스)
        - shift_amount: int | None       (양수=삽입, 음수=삭제, None=윈도우 초과)
        - insert_range: (start, end)     (즉시 수집 가능한 신규 데이터 위치, shift_amount>0일 때)
        - expected_lcns_no: str
        - bssh_nm: str
    """
    if not pivots:
        return False, {}

    pivot_items = list(pivots.items())
    sample_size = max(1, int(len(pivot_items) * sample_ratio))
    sampled = sorted(
        random.sample(pivot_items, min(sample_size, len(pivot_items))),
        key=lambda x: int(x[0])
    )

    sampled_indices = [int(k) for k, _ in sampled]
    idx_preview = ", ".join(f"{i:,}" for i in sampled_indices[:5])
    if len(sampled_indices) > 5:
        idx_preview += f" 외 {len(sampled_indices)-5}개"

    logger.info(
        f"[{service_id}][피벗 무결성 검사] 총 {len(pivot_items)}개 피벗 중 "
        f"{len(sampled)}개 샘플 검사 시작 → 인덱스: [{idx_preview}]"
    )

    for idx_str, pivot_data in sampled:
        idx = int(idx_str)
        if isinstance(pivot_data, dict):
            expected_lcns_no = pivot_data.get("LCNS_NO", "")
            expected_last_lcns_no = pivot_data.get("LAST_LCNS_NO", "")
            bssh_nm = pivot_data.get("BSSH_NM", "")
        else:
            expected_lcns_no = str(pivot_data)
            expected_last_lcns_no = ""
            bssh_nm = ""

        try:
            # ── Step 1: 단건 빠른 체크 ─────────────────────────────────────
            res = await api_client.fetch_data(service_id, idx, idx)
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
            items = res.get(service_id, {}).get("row", [])
            if not items:
                logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 응답 없음 → 스킵")
                continue

            actual_lcns_no = items[0].get("LCNS_NO", "")
            if actual_lcns_no == expected_lcns_no:
                # 첫 행 정상 → 마지막 행도 검증
                if expected_last_lcns_no:
                    last_res = await api_client.fetch_data(
                        service_id, idx + PAGE_SIZE - 1, idx + PAGE_SIZE - 1
                    )
                    await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
                    last_items = last_res.get(service_id, {}).get("row", [])
                    if last_items:
                        actual_last = last_items[0].get("LCNS_NO", "")
                        if actual_last != expected_last_lcns_no:
                            logger.warning(
                                f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 페이지 끝 행 불일치!\n"
                                f"  저장값(마지막): {expected_last_lcns_no}\n"
                                f"  현재값(마지막): {actual_last}\n"
                                f"  → {idx:,}~{idx+PAGE_SIZE-1:,} 경계 구간에 삽입 발생 가능성"
                            )
                            return True, {
                                "first_mismatch_idx": idx + PAGE_SIZE - 1,
                                "shift_amount": None,
                                "insert_range": None,
                                "expected_lcns_no": expected_last_lcns_no,
                                "bssh_nm": bssh_nm,
                            }
                continue  # 이 피벗 정상

            # ── Step 2: 불일치 감지! 1,000건 윈도우로 Shift 진단 ──────────
            logger.warning(
                f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 위치 불일치!\n"
                f"  저장값: {expected_lcns_no} ({bssh_nm or '업소명 미상'})\n"
                f"  현재값: {actual_lcns_no}"
            )
            logger.info(
                f"[{service_id}] 🔍 Shift 진단: {idx:,}~{idx+PAGE_SIZE-1:,} 구간 "
                f"1,000건 일괄 조회로 밀림 정도 측정 중..."
            )

            window_res = await api_client.fetch_data(service_id, idx, idx + PAGE_SIZE - 1)
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
            window_items = window_res.get(service_id, {}).get("row", [])

            shift_amount = None
            for i, row in enumerate(window_items):
                if row.get("LCNS_NO") == expected_lcns_no:
                    shift_amount = i  # i칸 뒤에서 발견됨 = i건 앞에 삽입됨
                    break

            shift_info = {
                "first_mismatch_idx": idx,
                "shift_amount": shift_amount,
                "insert_range": (idx, idx + shift_amount - 1) if shift_amount and shift_amount > 0 else None,
                "expected_lcns_no": expected_lcns_no,
                "bssh_nm": bssh_nm,
            }

            if shift_amount is not None and shift_amount > 0:
                logger.warning(
                    f"[{service_id}] 📊 Shift 진단 완료:\n"
                    f"  {idx:,}번 위치의 레코드가 {shift_amount}칸 뒤로 밀림\n"
                    f"  → 신규 {shift_amount}건이 [{idx:,} ~ {idx+shift_amount-1:,}] 구간에 삽입됨!\n"
                    f"  → 해당 구간 즉시 수집 가능"
                )
            elif shift_amount == 0:
                logger.warning(
                    f"[{service_id}] 📊 Shift=0: 동일 위치에서 레코드 자체가 교체됨 "
                    f"(제자리 수정 또는 다른 요인)"
                )
            else:
                logger.warning(
                    f"[{service_id}] 📊 Shift 진단 실패: {PAGE_SIZE}건 윈도우 내에서 "
                    f"{expected_lcns_no} 미발견 → 대규모 변동 또는 레코드 삭제 가능성"
                )

            return True, shift_info

        except Exception as e:
            logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 조회 실패 (무시): {e}")
            continue

    logger.info(
        f"[{service_id}][피벗 무결성 검사] ✅ {len(sampled)}개 샘플 전부 정상 — "
        f"API 데이터 재정렬 없음 확인됨."
    )
    return False, {}
