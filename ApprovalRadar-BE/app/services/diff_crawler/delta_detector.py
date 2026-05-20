from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event

PAGE_SIZE = 1000
SHIFT_EARLY_EXIT_THRESHOLD = 5

async def compute_shift_offsets(engine, pivots: dict, pivot_indices: list, diff_count: int) -> dict | None:
    """
    [Phase 1] 피벗별 Shift 오프셋을 메모리 기반 청크 스캔으로 계산합니다.
    연속 5개 피벗이 모두 미발견이면 API 전체 재정렬로 판단하여 None을 반환합니다.
    """
    svc = engine.service_id
    shift_amounts = {}
    current_shift = 0
    consecutive_miss = 0

    logger.info(
        f"[{svc}] ⏳ 피벗 Shift 분석 시작: 저장된 피벗 {len(pivot_indices)}개를 구간별로 스캔 "
        f"(diff_count={diff_count:,}, 조기중단={SHIFT_EARLY_EXIT_THRESHOLD}연속 미발견 시)"
    )
    for i, p_idx in enumerate(pivot_indices):
        old_data = pivots[str(p_idx)]
        expected_lcns_no = old_data["LCNS_NO"] if isinstance(old_data, dict) else str(old_data)
        expected_chng_dt = old_data.get("CHNG_DT", "") if isinstance(old_data, dict) else ""

        found_offset = current_shift
        found = False

        if i > 0:
            prev_p_idx = pivot_indices[i - 1]
            prev_shift = shift_amounts.get(prev_p_idx, current_shift)
            search_start = max(prev_p_idx + prev_shift + 1, p_idx - diff_count)
        else:
            search_start = max(1, p_idx - diff_count)
        search_end = p_idx + diff_count
        current_search_pos = search_start

        logger.debug(
            f"[{svc}] [청크 스캔] p_idx={p_idx:,} "
            f"탐색범위=[{search_start:,}~{search_end:,}] "
            f"(앞 구간 확장: {max(0, p_idx - search_start):,}건 추가 커버)"
        )

        while current_search_pos <= search_end and not found and not shutdown_event.is_set():
            chunk_end = min(current_search_pos + PAGE_SIZE - 1, search_end)
            rows = await engine._fetch_page(current_search_pos, chunk_end)

            for j, row in enumerate(rows):
                if (
                    row.get("LCNS_NO") == expected_lcns_no
                    and row.get("CHNG_DT") == expected_chng_dt
                ):
                    found_offset = (current_search_pos - p_idx) + j
                    found = True
                    break

            current_search_pos += PAGE_SIZE

        if not found:
            consecutive_miss += 1
            logger.warning(
                f"[{svc}] ⚠️ [청크 스캔] p_idx={p_idx:,} 피벗 레코드 미발견 "
                f"(LCNS_NO={expected_lcns_no}). 연속 미발견: {consecutive_miss}/{SHIFT_EARLY_EXIT_THRESHOLD}"
            )
            if consecutive_miss >= SHIFT_EARLY_EXIT_THRESHOLD:
                logger.warning(
                    f"[{svc}] 🛑 연속 {consecutive_miss}개 피벗 미발견! "
                    f"API 전체 재정렬로 판단 → 피벗 Shift 분석 조기 중단."
                )
                return None
        else:
            consecutive_miss = 0
            logger.debug(
                f"[{svc}] [청크 스캔] p_idx={p_idx:,} → offset={found_offset} 확정"
            )

        shift_amounts[p_idx] = found_offset
        current_shift = found_offset

    shifted_pivots = [(p_idx, shift_amounts[p_idx]) for p_idx in pivot_indices if shift_amounts[p_idx] > 0]
    if shifted_pivots:
        first_shifted_idx = shifted_pivots[0][0]
        logger.info(
            f"[{svc}] 📍 피벗 분석 결과: "
            f"{first_shifted_idx:,}번 인덱스 앞에서 Shift 발생 → "
            f"해당 구간에 신규 데이터 삽입 가능성 확인"
        )
    else:
        logger.info(f"[{svc}] 피벗 분석 결과: 모든 피벗 Shift=0 (데이터 Tail단 추가)")
    return shift_amounts


async def download_new_rows(engine, pivot_indices: list, shift_amounts: dict, old_tail: int, new_tail: int, diff_count: int) -> list:
    """신규 삽입된 행들을 구간별로 다운로드합니다."""
    svc = engine.service_id
    new_data_rows = []
    prev_idx = 0
    prev_shift = 0
    segments = []

    for p_idx in pivot_indices:
        shift = shift_amounts[p_idx]
        if shift > prev_shift:
            segments.append((prev_idx + 1, p_idx, shift - prev_shift, prev_shift))
        prev_idx = p_idx
        prev_shift = shift

    if prev_shift < diff_count:
        segments.append((prev_idx + 1, new_tail, diff_count - prev_shift, prev_shift))

    for seg_start, seg_end, count, base_shift in segments:
        new_start = seg_start + base_shift
        new_end = seg_end + base_shift + count
        logger.info(
            f"[{svc}] 📥 피벗 조사 결과: "
            f"{seg_start:,}당~{seg_end:,}당 구간에 신규 데이터 {count}건 존재 가능성 포착!"
            f" (API 실제 요청 범위: {new_start:,}~{new_end:,})"
        )
        fetched_rows = []
        current_start = new_start
        while current_start <= new_end:
            current_end = min(current_start + PAGE_SIZE - 1, new_end)
            rows = await engine._fetch_page(current_start, current_end)
            fetched_rows.extend(rows)
            current_start += PAGE_SIZE

        if fetched_rows:
            fetched_rows.sort(key=lambda x: x.get("CHNG_DT", ""), reverse=True)
            top_new = fetched_rows[:count]
            for r in top_new:
                r["DB_INDEX_RANGE"] = f"{new_start}~{new_end}"
            new_data_rows.extend(top_new)

    return new_data_rows


async def update_pivots(engine, pivot_indices: list, pivots: dict, shift_amounts: dict, new_tail: int, diff_count: int) -> dict:
    """[Phase 2] 피벗 인덱스를 Shift 오프셋에 맞게 갱신하고, 새 꼬리까지 추가 피벗을 생성합니다."""
    svc = engine.service_id
    new_pivots = {}
    for p_idx in pivot_indices:
        shift = shift_amounts[p_idx]
        new_p_idx = p_idx + shift
        new_pivots[str(new_p_idx)] = pivots[str(p_idx)]

    max_pivot = max(pivot_indices) if pivot_indices else 0
    next_pivot = (
        (max_pivot + shift_amounts.get(max_pivot, diff_count)) // settings.PIVOT_INTERVAL + 1
    ) * settings.PIVOT_INTERVAL
    while next_pivot < new_tail:
        rows = await engine._fetch_page(next_pivot, next_pivot + PAGE_SIZE - 1)
        if rows:
            from app.services.pivot_manager import compute_page_fingerprint
            row = rows[0]
            last_row = rows[-1]
            new_pivots[str(next_pivot)] = {
                "LCNS_NO": row.get("LCNS_NO", ""),
                "LAST_LCNS_NO": last_row.get("LCNS_NO", ""),
                "CHNG_DT": row.get("CHNG_DT", ""),
                "BSSH_NM": row.get("BSSH_NM", ""),
                "fingerprint": compute_page_fingerprint(rows),
            }
            logger.debug(
                f"[{svc}] [피벗 생성] idx={next_pivot:,} "
                f"LCNS_NO={row.get('LCNS_NO','')} ~ {last_row.get('LAST_LCNS_NO','')}"
            )
        next_pivot += settings.PIVOT_INTERVAL

    return new_pivots
