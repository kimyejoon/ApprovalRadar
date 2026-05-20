import asyncio
from app.core.logger import logger
from app.core.events import shutdown_event
from app.services.crawler_constants import PAGE_SIZE, RELIABLE_TOTAL_COUNT_SERVICES
from app.services.api_utils import fetch_page

class TailExplorer:
    def __init__(self, api_client, service_id: str, state_repo):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = state_repo
        self.reshuffled: bool = False

    async def _exponential_jump(self, start_pos: int) -> tuple[int, int]:
        pos = start_pos
        last_nonempty = pos
        while not shutdown_event.is_set():
            rows = await fetch_page(self.api_client, self.service_id, pos, pos + PAGE_SIZE - 1)
            if rows:
                last_nonempty = pos
                logger.info(f"[{self.service_id}][Bootstrapper] 지수점프 {pos:,}: {len(rows)}건")
                pos *= 2
                if pos > 50_000_000:
                    break
            else:
                break
        return last_nonempty, pos

    async def find_true_tail(self, known_tail: int = 0) -> int:
        svc = self.service_id

        if svc in RELIABLE_TOTAL_COUNT_SERVICES:
            logger.info(f"[{svc}][전략A] total_count 직접 조회 (Ping 스킵)")
            res = await self.api_client.fetch_data(svc, 1, 1, timeout=10)
            if res and svc in res:
                block = res[svc]
                if block.get("RESULT", {}).get("CODE") in ("INFO-000", "INFO-200"):
                    total_count = int(block.get("total_count") or block.get("TOTAL_COUNT") or 0)
                    if total_count > 0:
                        if known_tail > 0 and total_count < known_tail * 0.5:
                            logger.warning(
                                f"[{svc}][전략A] ⚠️ total_count={total_count:,}이 "
                                f"known_tail={known_tail:,}의 50% 미만 — API 오응답 의심. "
                                f"전략B(이진탐색)로 자동 전환합니다."
                            )
                        elif known_tail > 0 and total_count == known_tail:
                            logger.debug(f"[{svc}][전략A] 변동 없음: total_count={total_count:,} == known_tail={known_tail:,}")
                            logger.info(f"[{svc}] ✔️ Tail 조사 완료: 현재 전체 {total_count:,}건 — 이번 주기 신규 인허가변동 없음.")
                            return total_count
                        elif total_count > known_tail:
                            logger.info(f"[{svc}] 🚨 Tail 조사 결과: 전체 {total_count:,}건 감지 → 이전({known_tail:,})보다 +{total_count - known_tail:,}건 신규 인허가변동 가능성 포착!")
                            return total_count
                        else:
                            logger.info(f"[{svc}][전략A] Tail 확정: {total_count:,}건 (total_count 직접)")
                            return total_count
            logger.warning(f"[{svc}][전략A] total_count 읽기 실패 또는 오응답, 페이지 탐색(전략B)으로 폴백")

        logger.info(f"[{svc}][Bootstrapper] Tail 탐색 시작 (known_tail={known_tail:,})")

        if known_tail > 0:
            range_start = max(1, known_tail - PAGE_SIZE + 1)
            tail_check = await fetch_page(self.api_client, svc, range_start, known_tail)
            if not tail_check:
                logger.warning(
                    f"[{svc}] ⚠️ known_tail={known_tail:,} 근방 [{range_start:,}~{known_tail:,}] "
                    f"범위에 데이터 없음! API 재정렬/축소 감지. 이진탐색으로 실제 tail 재탐색..."
                )
                self.reshuffled = True
                known_tail = 0
            else:
                ping = await fetch_page(self.api_client, svc, known_tail + 1, known_tail + PAGE_SIZE)
                if not ping:
                    logger.info(
                        f"[{svc}] ✔️ Tail 조사 완료: 현재 전체 {known_tail:,}건 — "
                        f"{known_tail+1:,}번 이후 데이터 없음 → 이번 주기 신규 발생 없음."
                    )
                    return known_tail
                logger.info(f"[{svc}] 📌 Ping: {known_tail+1:,}번 이후에 {len(ping)}건 데이터 감지 → 정확한 신규 건수 탐색 시작...")

        if known_tail == 0:
            first_page = await fetch_page(self.api_client, svc, 1, PAGE_SIZE)
            if not first_page:
                logger.info(f"[{svc}][전략B] Pre-check: 데이터 없음 (tail=0)")
                state = {"last_total_count": 0, "pivots": {}}
                self.state_repo.save_state(svc, state)
                return 0
            if len(first_page) < PAGE_SIZE:
                final_tail = len(first_page)
                logger.info(f"[{svc}][전략B] Pre-check: 소규모 데이터 감지 — tail={final_tail:,}건 (< PAGE_SIZE={PAGE_SIZE:,}). 지수점프 스킵.")
                logger.info(f"[{svc}][Bootstrapper] Tail 확정: {final_tail:,}")
                return final_tail
            logger.debug(f"[{svc}][전략B] Pre-check: 정상 규모 ({PAGE_SIZE:,}건) → 지수점프 진행")

        start_pos = max(PAGE_SIZE, known_tail + PAGE_SIZE)
        last_nonempty, upper_bound = await self._exponential_jump(start_pos)

        low, high = last_nonempty, upper_bound
        logger.info(f"[{svc}][Bootstrapper] 이진탐색 범위: {low:,} ~ {high:,}")

        best_start = low
        while high - low >= PAGE_SIZE and not shutdown_event.is_set():
            mid = ((low + high) // 2 // PAGE_SIZE) * PAGE_SIZE
            if await fetch_page(self.api_client, svc, mid, mid + PAGE_SIZE - 1):
                best_start = mid
                low = mid + PAGE_SIZE
            else:
                high = mid

        MAX_GAP_PAGES = 3
        pos, final_tail, consecutive_empty = best_start, best_start, 0
        while not shutdown_event.is_set():
            rows = await fetch_page(self.api_client, svc, pos, pos + PAGE_SIZE - 1)
            if rows:
                final_tail = pos + len(rows) - 1
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty >= MAX_GAP_PAGES:
                    break
            pos += PAGE_SIZE

        logger.info(f"[{svc}][Bootstrapper] Tail 확정: {final_tail:,}")
        return final_tail
