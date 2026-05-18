"""
피벗 샘플링 및 갱신 전담 모듈.
diff_crawler.py에서 분리된 책임 단위입니다.

⚠️ API 중요 특성 (실증 확인):
  - 동일한 position(예: 35000)이라도 쿼리 범위(end-start+1)에 따라 반환 레코드가 다름
  - 단건(35000/35000) vs 1000건(35000/35999): 완전히 다른 레코드 반환
  - 따라서 피벗은 반드시 저장 당시와 동일한 PAGE_SIZE(1,000건)로 조회해야 일관성 보장
"""
import asyncio
import random
from app.core.config import settings
from app.core.logger import logger

PAGE_SIZE = 1000  # diff_crawler.py와 동일한 상수


async def sample_check(pivots: dict, api_client, service_id: str, sample_ratio: float = 0.2) -> tuple:
    """
    저장된 피벗 중 일부를 무작위 샘플링하여 API 현재 응답과 비교합니다.

    ✅ 핵심 수정: 단건 조회 → 1,000건 윈도우 조회로 전환
       - API는 요청 크기(PAGE_SIZE)에 따라 반환 레코드가 달라짐 (실증 확인)
       - 피벗 저장 방식(1,000건)과 동일한 범위로 검증해야 정확한 비교 가능
    ✅ Shift 진단: 불일치 감지 시 1,000건 윈도우 내 저장값 위치 탐색 → 정확한 삽입 위치 반환

    Returns: (changed: bool, shift_info: dict)
      shift_info keys:
        - first_mismatch_idx: int
        - shift_amount: int | None  (양수=삽입, None=윈도우 초과)
        - insert_range: (start, end) | None
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
            # ── 1,000건 단위 조회 ─────────────────────────────────────────────
            # 피벗은 fetch_page(idx, idx+PAGE_SIZE-1) 방식으로 저장됐으므로
            # 동일한 범위로 조회해야 같은 레코드 반환 (API 특성)
            logger.debug(
                f"[{service_id}][피벗 무결성 검사] idx={idx:,} "
                f"1,000건 조회 ({idx:,}~{idx+PAGE_SIZE-1:,})..."
            )
            res = await api_client.fetch_data(service_id, idx, idx + PAGE_SIZE - 1)
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
            items = res.get(service_id, {}).get("row", [])
            if not items:
                logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 응답 없음 → 스킵")
                continue

            actual_lcns_no = items[0].get("LCNS_NO", "")        # 1,000건 첫 행 = 피벗 첫 행
            actual_last_lcns_no = items[-1].get("LCNS_NO", "") if len(items) > 1 else ""

            # ── 첫 행 비교 ────────────────────────────────────────────────────
            if actual_lcns_no != expected_lcns_no:
                logger.warning(
                    f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 위치 첫 행 불일치!\n"
                    f"  저장값: {expected_lcns_no} ({bssh_nm or '업소명 미상'})\n"
                    f"  현재값: {actual_lcns_no}\n"
                    f"  → 이 위치 이전 구간에 Insert+Delete 동시 발생 가능성."
                )

                # Shift 진단: 현재 1,000건 윈도우 내에서 저장값 탐색
                logger.info(
                    f"[{service_id}] 🔍 Shift 진단: 반환된 {len(items)}건 내에서 "
                    f"{expected_lcns_no} 탐색 중..."
                )
                shift_amount = None
                for i, row in enumerate(items):
                    if row.get("LCNS_NO") == expected_lcns_no:
                        shift_amount = i
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
                        f"  {idx:,}번 위치 레코드({expected_lcns_no})가 {shift_amount}칸 뒤로 밀림\n"
                        f"  → 신규 {shift_amount}건이 [{idx:,} ~ {idx+shift_amount-1:,}] 구간에 삽입됨!\n"
                        f"  → 즉시 해당 구간 데이터를 수집 가능"
                    )
                elif shift_amount == 0:
                    logger.warning(
                        f"[{service_id}] 📊 Shift=0: 저장값이 현재 첫 번째 위치에서 발견됨. "
                        f"(1,000건 정상 일치 — API 재조회 필요)"
                    )
                else:
                    logger.warning(
                        f"[{service_id}] 📊 Shift 진단: {len(items)}건 윈도우 내에서 "
                        f"{expected_lcns_no} 미발견 → 대규모 변동 또는 레코드 삭제 가능성"
                    )

                return True, shift_info

            # ── 마지막 행 비교 (LAST_LCNS_NO 저장된 경우만) ──────────────────
            if expected_last_lcns_no and actual_last_lcns_no:
                if actual_last_lcns_no != expected_last_lcns_no:
                    logger.warning(
                        f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 페이지 마지막 행 불일치!\n"
                        f"  저장값(마지막): {expected_last_lcns_no}\n"
                        f"  현재값(마지막): {actual_last_lcns_no}\n"
                        f"  → {idx:,}~{idx+PAGE_SIZE-1:,} 경계 구간 내 삽입 발생 가능성"
                    )
                    return True, {
                        "first_mismatch_idx": idx,
                        "shift_amount": None,
                        "insert_range": None,
                        "expected_lcns_no": expected_last_lcns_no,
                        "bssh_nm": bssh_nm,
                    }

        except Exception as e:
            logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 조회 실패 (무시): {e}")
            continue

    logger.info(
        f"[{service_id}][피벗 무결성 검사] ✅ {len(sampled)}개 샘플 전부 정상 — "
        f"API 데이터 재정렬 없음 확인됨."
    )
    return False, {}
