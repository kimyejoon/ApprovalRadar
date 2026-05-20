import asyncio
from app.core.logger import logger
from app.core.events import shutdown_event
from app.core.config import settings
from app.services.crawler_constants import PAGE_SIZE
from app.services.api_utils import fetch_page

class PivotAnalyzer:
    def __init__(self, api_client, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.SHIFT_EARLY_EXIT_THRESHOLD = 5

    async def compute_shift_offsets(self, pivots: dict, pivot_indices: list, diff_count: int) -> dict | None:
        shift_amounts = {}
        current_shift = 0
        consecutive_miss = 0

        logger.info(f"[{self.service_id}] ⏳ 피벗 Shift 분석 시작: 저장된 피벗 {len(pivot_indices)}개를 구간별로 스캔 (diff_count={diff_count:,}, 조기중단={self.SHIFT_EARLY_EXIT_THRESHOLD}연속 미발견 시)")
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

            logger.debug(f"[{self.service_id}] [청크 스캔] p_idx={p_idx:,} 탐색범위=[{search_start:,}~{search_end:,}] (앞 구간 확장: {max(0, p_idx - search_start):,}건 추가 커버)")

            while current_search_pos <= search_end and not found and not shutdown_event.is_set():
                chunk_end = min(current_search_pos + PAGE_SIZE - 1, search_end)
                rows = await fetch_page(self.api_client, self.service_id, current_search_pos, chunk_end)

                for j, row in enumerate(rows):
                    if row.get("LCNS_NO") == expected_lcns_no and row.get("CHNG_DT") == expected_chng_dt:
                        found_offset = (current_search_pos - p_idx) + j
                        found = True
                        break

                current_search_pos += PAGE_SIZE

            if not found:
                consecutive_miss += 1
                logger.warning(f"[{self.service_id}] ⚠️ [청크 스캔] p_idx={p_idx:,} 피벗 레코드 미발견 (LCNS_NO={expected_lcns_no}). 연속 미발견: {consecutive_miss}/{self.SHIFT_EARLY_EXIT_THRESHOLD}")
                if consecutive_miss >= self.SHIFT_EARLY_EXIT_THRESHOLD:
                    logger.warning(f"[{self.service_id}] 🛑 연속 {consecutive_miss}개 피벗 미발견! API 전체 재정렬로 판단 → 피벗 Shift 분석 조기 중단. 재부트스트랩으로 전환합니다. (잔여 피벗 {len(pivot_indices) - i - 1}개 스킵)")
                    return None
            else:
                consecutive_miss = 0
                logger.debug(f"[{self.service_id}] [청크 스캔] p_idx={p_idx:,} → offset={found_offset} 확정")

            shift_amounts[p_idx] = found_offset
            current_shift = found_offset

        shifted_pivots = [(p_idx, shift_amounts[p_idx]) for p_idx in pivot_indices if shift_amounts[p_idx] > 0]
        if shifted_pivots:
            first_shifted_idx = shifted_pivots[0][0]
            logger.info(f"[{self.service_id}] 📍 피벗 분석 결과: {first_shifted_idx:,}번 인덱스 앞에서 Shift 발생 → 해당 구간에 신규 데이터 삽입 가능성 확인")
        else:
            logger.info(f"[{self.service_id}] 피벗 분석 결과: 모든 피벗 Shift=0 (데이터 Tail단 추가)")
        return shift_amounts

    async def update_pivots(self, pivot_indices: list, pivots: dict, shift_amounts: dict, new_tail: int, diff_count: int) -> dict:
        new_pivots = {}
        for p_idx in pivot_indices:
            shift = shift_amounts[p_idx]
            new_p_idx = p_idx + shift
            new_pivots[str(new_p_idx)] = pivots[str(p_idx)]

        max_pivot = max(pivot_indices) if pivot_indices else 0
        next_pivot = ((max_pivot + shift_amounts.get(max_pivot, diff_count)) // settings.PIVOT_INTERVAL + 1) * settings.PIVOT_INTERVAL
        while next_pivot < new_tail:
            rows = await fetch_page(self.api_client, self.service_id, next_pivot, next_pivot + PAGE_SIZE - 1)
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
                logger.debug(f"[{self.service_id}] [피벗 생성] idx={next_pivot:,} LCNS_NO={row.get('LCNS_NO','')} ~ {last_row.get('LCNS_NO','')}")
            next_pivot += settings.PIVOT_INTERVAL

        return new_pivots
