"""
피벗 샘플링 및 갱신 전담 모듈.
diff_crawler.py에서 분리된 책임 단위입니다.

핵심 설계 원칙:
  1. (LCNS_NO, CHNG_DT) 복합키 사용 — 인허가 변동분 DB 특성 반영
     (동일 업소가 여러 건의 변동분을 가질 수 있으므로 LCNS_NO 단독 사용 불가)
  2. 1,000건 단위 조회 고정 — API 특성상 요청 범위(PAGE_SIZE)에 따라 반환 레코드가 달라짐
     (실증: 35000/35000 단건 vs 35000/35999 1000건은 완전히 다른 레코드 반환)
  3. fingerprint 기반 전체 대조 — 1,000건 모두의 복합키를 해시하여 한 번에 비교
  4. Shift 진단 — 불일치 시 새로 삽입된 레코드 목록과 위치를 즉시 특정
"""
import asyncio
import hashlib
import json
import random
from app.core.config import settings
from app.core.logger import logger

PAGE_SIZE = 1000  # diff_crawler.py와 동일한 상수


def compute_page_fingerprint(rows: list) -> str:
    """
    1,000건의 (LCNS_NO, CHNG_DT) 복합키 순서 목록의 MD5 해시.
    동일한 1,000건이 동일한 순서로 있으면 반드시 같은 fingerprint를 반환.
    """
    keys = [(r.get("LCNS_NO", ""), r.get("CHNG_DT", "")) for r in rows]
    return hashlib.md5(json.dumps(keys, ensure_ascii=False).encode()).hexdigest()


async def sample_check(pivots: dict, api_client, service_id: str, sample_ratio: float = 0.2) -> tuple:
    """
    저장된 피벗 페이지를 1,000건 단위로 전체 조회하여 fingerprint 비교.

    알고리즘:
      1. 무작위 샘플 피벗 선택 (sample_ratio%)
      2. 각 피벗을 1,000건 일괄 조회 (저장 당시와 동일한 PAGE_SIZE)
      3. 현재 (LCNS_NO, CHNG_DT) 복합키 fingerprint 계산
      4. 저장된 fingerprint와 비교 → 완전 일치 시 정상
      5. 불일치 시:
         a. 저장된 첫 번째 복합키를 현재 records에서 탐색
         b. i번째에서 발견 → shift_amount = i (i건이 앞에 새로 삽입됨)
         c. 삽입된 records 상세 로그 출력

    Returns: (changed: bool, shift_info: dict)
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

    api_calls_before = getattr(api_client, "_call_count", 0)
    logger.info(
        f"[{service_id}][피벗 무결성 검사] 총 {len(pivot_items)}개 피벗 중 "
        f"{len(sampled)}개 샘플 선택 → 각 1,000건 전체 대조 시작\n"
        f"  검사 인덱스: [{idx_preview}]"
    )

    for idx_str, pivot_data in sampled:
        idx = int(idx_str)

        if not isinstance(pivot_data, dict):
            logger.debug(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 레거시 포맷 → 스킵")
            continue

        stored_lcns_no = pivot_data.get("LCNS_NO", "")
        stored_chng_dt = pivot_data.get("CHNG_DT", "")
        stored_fingerprint = pivot_data.get("fingerprint", "")
        bssh_nm = pivot_data.get("BSSH_NM", "")

        try:
            # ── 1,000건 일괄 조회 + 상세 페이지/API 로깅 ───────────────────
            page_end = idx + PAGE_SIZE - 1
            call_seq = getattr(api_client, "_call_count", 0) - api_calls_before + 1
            logger.info(
                f"[{service_id}][피벗 무결성 검사] 📡 API 호출 #{call_seq}: "
                f"pages {idx:,}~{page_end:,} (1,000건 범위) 조회 중..."
            )
            res = await api_client.fetch_data(service_id, idx, page_end)
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
            items = res.get(service_id, {}).get("row", [])
            total_from_api = res.get(service_id, {}).get("total_count", "?")

            if not items:
                logger.info(f"[{service_id}][피벗 무결성 검사] idx={idx:,} 응답 없음 → 스킵")
                continue

            logger.info(
                f"[{service_id}][피벗 무결성 검사] ✉️  pages {idx:,}~{page_end:,} 응답 수신: "
                f"{len(items)}건 (API total_count={total_from_api})"
            )

            # ── Fingerprint 전체 대조 ─────────────────────────────────────
            current_fingerprint = compute_page_fingerprint(items)

            if stored_fingerprint and current_fingerprint == stored_fingerprint:
                logger.info(
                    f"[{service_id}][피벗 무결성 검사] ✅ pages {idx:,}~{page_end:,} "
                    f"fingerprint 일치 — {len(items)}건 전체 정상"
                )
                continue

            # ── 불일치 감지 ───────────────────────────────────────────────
            if stored_fingerprint:
                logger.warning(
                    f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 피벗 "
                    f"fingerprint 불일치! (pages {idx:,}~{page_end:,}, 1,000건 전체 변동 감지)\n"
                    f"  저장 지문: {stored_fingerprint[:12]}...\n"
                    f"  현재 지문: {current_fingerprint[:12]}..."
                )
            else:
                actual_first_key = (items[0].get("LCNS_NO", ""), items[0].get("CHNG_DT", ""))
                stored_first_key = (stored_lcns_no, stored_chng_dt)
                if actual_first_key == stored_first_key:
                    logger.info(
                        f"[{service_id}][피벗 무결성 검사] idx={idx:,} "
                        f"복합키 일치 (fingerprint 미저장 피벗) → 정상으로 간주"
                    )
                    continue
                logger.warning(
                    f"[{service_id}][피벗 무결성 검사] ❌ {idx:,}번 피벗 복합키 불일치!\n"
                    f"  저장값: ({stored_lcns_no}, {stored_chng_dt}) [{bssh_nm}]\n"
                    f"  현재값: {actual_first_key}"
                )

            # ── Shift 진단: 저장된 첫 번째 복합키를 현재 records에서 선형 탐색 ──
            stored_first_key = (stored_lcns_no, stored_chng_dt)
            logger.info(
                f"[{service_id}] 🔍 Shift 진단: pages {idx:,}~{page_end:,}의 {len(items)}건 내에서 "
                f"({stored_lcns_no}, {stored_chng_dt}) [{bssh_nm}] 탐색 중..."
            )

            shift_amount = None
            new_rows = []

            for i, row in enumerate(items):
                current_key = (row.get("LCNS_NO", ""), row.get("CHNG_DT", ""))
                if current_key == stored_first_key:
                    shift_amount = i
                    new_rows = items[:i]
                    break

            shift_info = {
                "first_mismatch_idx": idx,
                "shift_amount": shift_amount,
                "insert_range": (idx, idx + shift_amount - 1) if shift_amount and shift_amount > 0 else None,
                "new_rows": new_rows,
                "expected_lcns_no": stored_lcns_no,
                "bssh_nm": bssh_nm,
            }

            api_calls_used = getattr(api_client, "_call_count", 0) - api_calls_before

            if shift_amount is not None and shift_amount > 0:
                new_rows_summary = "\n".join(
                    f"    [{i+1}] {r.get('BSSH_NM', '업소명미상')} "
                    f"(LCNS_NO={r.get('LCNS_NO', '')}, CHNG_DT={r.get('CHNG_DT', '')})"
                    for i, r in enumerate(new_rows[:10])
                )
                if len(new_rows) > 10:
                    new_rows_summary += f"\n    ... 외 {len(new_rows)-10}건"
                logger.warning(
                    f"[{service_id}] 📊 Shift 진단 완료:\n"
                    f"  {idx:,}번 피벗의 첫 레코드가 {shift_amount}칸 뒤로 밀림\n"
                    f"  → 신규 삽입 {shift_amount}건 상세:\n{new_rows_summary}\n"
                    f"  → [{idx:,} ~ {idx+shift_amount-1:,}] 구간 즉시 수집 가능\n"
                    f"  📡 피벗 검사 누적 API 호출: {api_calls_used}회 소모"
                )
            elif shift_amount == 0:
                logger.warning(
                    f"[{service_id}] 📊 Shift=0: pages {idx:,}~{page_end:,} — "
                    f"저장된 복합키가 records[0]과 일치하나 fingerprint 다름\n"
                    f"  → 페이지 중간/끝 부분 레코드 교체·삭제 발생 추정\n"
                    f"  📡 피벗 검사 누적 API 호출: {api_calls_used}회 소모"
                )
            else:
                logger.warning(
                    f"[{service_id}] 📊 Shift 진단 실패: pages {idx:,}~{page_end:,}의 {len(items)}건 내에서 "
                    f"복합키({stored_lcns_no}, {stored_chng_dt}) 미발견\n"
                    f"  → 대규모 변동(>1,000건) 또는 해당 레코드 자체 삭제 가능성\n"
                    f"  📡 피벗 검사 누적 API 호출: {api_calls_used}회 소모"
                )

            return True, shift_info

        except Exception as e:
            logger.warning(
                f"[{service_id}][피벗 무결성 검사] idx={idx:,} 조회 실패 (무시): {e}"
            )
            continue

    api_calls_used = getattr(api_client, "_call_count", 0) - api_calls_before
    logger.info(
        f"[{service_id}][피벗 무결성 검사] ✅ {len(sampled)}개 피벗 전체 정상 — "
        f"API 데이터 변동 없음 확인됨. (각 1,000건 fingerprint 대조)\n"
        f"  📡 총 API 호출 횟수: {api_calls_used}회 소모"
    )
    return False, {}
