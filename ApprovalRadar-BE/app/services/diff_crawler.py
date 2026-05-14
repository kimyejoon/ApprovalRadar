import asyncio
import random
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.core.events import shutdown_event
from app.services import pivot_manager

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수

# total_count 필드가 신뢰 가능한 서비스 목록
# → 1회 API 호출로 정확한 Tail을 바로 얻을 수 있음 (페이지 스캔 불필요)
# I2859: total_count 신뢰 불가 (API 버그로 9 등 엉뚱한 값 반환) → 페이지 스캔 사용
# I2861: 음식점업소 인허가변경 - 이벤트 로그 append 구조로 total_count가 정확
RELIABLE_TOTAL_COUNT_SERVICES = {"I2861"}


class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()

    # ─── 저수준 API 유틸리티 ──────────────────────────────────────────────────

    async def _fetch_page(self, start: int, end: int) -> list:
        """
        [start, end] 범위의 레코드를 비동기 조회하여 row 리스트를 반환합니다.
        bulk 응답 지연을 고려해 30초 timeout 사용.
        - INFO-000: 정상 데이터 리스트 반환
        - INFO-200: 빈 페이지(데이터 없음) → [] 반환
        - 기타 오류: [] 반환
        WAF 차단 방지를 위해 호출 후 Jitter(무작위 지연) 적용.
        """
        res = await self.api_client.fetch_data(self.service_id, start, end, timeout=30)
        # WAF 차단 방지: API 호출 직후 무작위 지연
        await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
        if not res or self.service_id not in res:
            return []
        block = res[self.service_id]
        code = block['RESULT']['CODE']
        if code == "INFO-000":
            return block.get('row', [])
        return []

    async def _fetch_single(self, idx: int) -> dict | None:
        """특정 단일 인덱스 1건 비동기 조회 (피벗 확인용). 단건이므로 10초 timeout.
        WAF 차단 방지를 위해 호출 후 Jitter(무작위 지연) 적용.
        """
        rows = await self.api_client.fetch_data(self.service_id, idx, idx, timeout=10)
        # WAF 차단 방지: API 호출 직후 무작위 지연
        await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
        if not rows or self.service_id not in rows:
            return None
        block = rows[self.service_id]
        code = block['RESULT']['CODE']
        if code == "INFO-000" and 'row' in block and block['row']:
            return block['row'][0]
        return None

    # ─── Tail 탐색 ────────────────────────────────────────────────────────────

    async def _exponential_jump(self, start_pos: int) -> tuple[int, int]:
        """
        지수 점프로 데이터 없는 상한선을 탐색합니다.
        Returns: (last_nonempty, upper_bound)
        """
        pos = start_pos
        last_nonempty = pos
        while not shutdown_event.is_set():
            rows = await self._fetch_page(pos, pos + PAGE_SIZE - 1)
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
        """
        실제 데이터 끝(Tail) 위치를 정확하게 탐색합니다.

        ⚠️ API 특성: Gappy(비연속) 인덱스 구조 (테스트로 실증)
        - total_count 신뢰 불가: 키/범위마다 다른 값 반환
        - 순차 페이지 스캔 오탐: Gap(예: 34756~34999 공백)에서 조기 종료
          → 34,755에서 멈췄으나 실제 tail ~226,000 (2025년 데이터)
        - 새 데이터: 항상 HIGH-END 인덱스에 추가 (CHNG_DT 기준 확인)

        알고리즘 4단계:
          1. [Ping]     known_tail+1 빠른 조회 → 변동 없으면 즉시 반환
          2. [지수점프]  PAGE*1, PAGE*2, PAGE*4... 데이터 없는 상한선 탐색
          3. [이진탐색]  마지막 데이터 있는 PAGE 경계를 O(log N)으로 확정
          4. [Gap허용]   빈 PAGE 연속 3개 미만이면 Gap으로 간주하고 계속 탐색
        """
        svc = self.service_id

        # ── 전략 A: total_count 신뢰 서비스 ──────────────────────────────────────
        # I2861 등 total_count가 신뢰 가능한 서비스: Ping 없이 1/1 조회로 즉시 판단
        if svc in RELIABLE_TOTAL_COUNT_SERVICES:
            logger.info(f"[{svc}][전략A] total_count 직접 조회 (Ping 스킵)")
            res = await self.api_client.fetch_data(svc, 1, 1, timeout=10)
            if res and svc in res:
                block = res[svc]
                if block.get("RESULT", {}).get("CODE") in ("INFO-000", "INFO-200"):
                    total_count = int(block.get("total_count") or block.get("TOTAL_COUNT") or 0)
                    if total_count > 0:
                        if known_tail > 0 and total_count == known_tail:
                            logger.debug(f"[{svc}][전략A] 변동 없음: total_count={total_count:,} == known_tail={known_tail:,}")
                        elif total_count > known_tail:
                            logger.info(f"[{svc}][전략A] 신규 감지: {total_count - known_tail:,}건 증가 ({known_tail:,} → {total_count:,})")
                        else:
                            logger.info(f"[{svc}][전략A] Tail 확정: {total_count:,}건 (total_count 직접)")
                        return total_count
            logger.warning(f"[{svc}][전략A] total_count 읽기 실패, 페이지 탐색(전략B)으로 폴백")

        # ── 전략 B: 지수점프 + 이진탐색 + Gap허용 스캔 ───────────────────────
        logger.info(f"[{svc}][Bootstrapper] Tail 탐색 시작 (known_tail={known_tail:,})")

        # Step 1: Ping - known_tail 직후 확인 (빠른 경로). 전략A 성공 서비스는 여기 미도달.
        if known_tail > 0:
            ping = await self._fetch_page(known_tail + 1, known_tail + PAGE_SIZE)
            if not ping:
                logger.info(f"[{svc}][전략B] Ping: 변동 없음 ({known_tail:,}건)")
                return known_tail
            logger.info(f"[{svc}][전략B] Ping: {len(ping)}건 신규 감지, 탐색 계속")


        # Step 2: 지수 점프
        start_pos = max(PAGE_SIZE, known_tail + PAGE_SIZE)
        last_nonempty, upper_bound = await self._exponential_jump(start_pos)

        low, high = last_nonempty, upper_bound
        logger.info(f"[{svc}][Bootstrapper] 이진탐색 범위: {low:,} ~ {high:,}")

        # Step 3: 이진 탐색 - 마지막 데이터 PAGE 경계 확정
        best_start = low
        while high - low >= PAGE_SIZE and not shutdown_event.is_set():
            mid = ((low + high) // 2 // PAGE_SIZE) * PAGE_SIZE
            if await self._fetch_page(mid, mid + PAGE_SIZE - 1):
                best_start = mid
                low = mid + PAGE_SIZE
            else:
                high = mid

        # Step 4: Gap 허용 선형 스캔 - 정확한 tail 확정
        # 연속 빈 PAGE가 MAX_GAP_PAGES 이상이면 실제 끝으로 판단
        MAX_GAP_PAGES = 3
        pos, final_tail, consecutive_empty = best_start, best_start, 0
        while not shutdown_event.is_set():
            rows = await self._fetch_page(pos, pos + PAGE_SIZE - 1)
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

    # ─── 부트스트랩 ───────────────────────────────────────────────────────────

    async def bootstrap(self):
        """처음부터 피벗을 생성합니다."""
        total_count = await self.find_true_tail(known_tail=0)
        pivots = {}

        logger.info(f"[{self.service_id}][Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
        pivot_indices = list(range(settings.PIVOT_INTERVAL, total_count, settings.PIVOT_INTERVAL))

        # ✅ asyncio.gather로 피벗 병렬 조회 (비동기 동시 실행)
        async def _fetch_pivot(idx: int):
            row = await self._fetch_single(idx)
            if row:
                last_row = await self._fetch_single(idx + PAGE_SIZE - 1)
                return idx, {
                    "LCNS_NO": row.get("LCNS_NO", ""),
                    "LAST_LCNS_NO": last_row.get("LCNS_NO", "") if last_row else "",
                    "CHNG_DT": row.get("CHNG_DT", ""),
                    "BSSH_NM": row.get("BSSH_NM", "")
                }
            return idx, None

        results = await asyncio.gather(*[_fetch_pivot(idx) for idx in pivot_indices])
        for idx, pivot_data in results:
            if pivot_data:
                pivots[str(idx)] = pivot_data

        state = {
            "last_total_count": total_count,
            "pivots": pivots
        }
        self.state_repo.save_state(self.service_id, state)
        logger.info(f"[{self.service_id}][Bootstrapper] 부트스트랩 완료! 총 {len(pivots)}개 피벗 색인 생성. (Tail: {total_count:,}건)")
        return state

    # ─── 델타 감지 ────────────────────────────────────────────────────────────

    async def _compute_shift_offsets(self, pivots: dict, pivot_indices: list, diff_count: int) -> dict:
        """피벗별 Shift 오프셋을 계산합니다."""
        shift_amounts = {}
        current_shift = 0

        logger.info(f"[{self.service_id}] ⚙️ 피벗 {len(pivot_indices)}개 Shift 오프셋 보정 시작...")
        for p_idx in pivot_indices:
            old_data = pivots[str(p_idx)]
            found_offset = current_shift
            for offset in range(current_shift, diff_count + 1):
                row = await self._fetch_single(p_idx + offset)
                if row and row.get("LCNS_NO") == old_data["LCNS_NO"] and row.get("CHNG_DT") == old_data["CHNG_DT"]:
                    found_offset = offset
                    break
            shift_amounts[p_idx] = found_offset
            current_shift = found_offset
        return shift_amounts

    async def _download_new_rows(self, pivot_indices: list, shift_amounts: dict, old_tail: int, new_tail: int, diff_count: int) -> list:
        """신규 삽입된 행들을 구간별로 다운로드합니다."""
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
                f"📥 [구간 {seg_start}~{seg_end}] 내에 {count}건의 중간 삽입 감지. "
                f"(실제 요청: {new_start}~{new_end}) 다운로드 진행..."
            )
            fetched_rows = []
            current_start = new_start
            while current_start <= new_end:
                current_end = min(current_start + PAGE_SIZE - 1, new_end)
                rows = await self._fetch_page(current_start, current_end)
                fetched_rows.extend(rows)
                current_start += PAGE_SIZE

            if fetched_rows:
                fetched_rows.sort(key=lambda x: x.get("CHNG_DT", ""), reverse=True)
                top_new = fetched_rows[:count]
                for r in top_new:
                    r["DB_INDEX_RANGE"] = f"{new_start}~{new_end}"
                new_data_rows.extend(top_new)

        return new_data_rows

    async def _update_pivots(self, pivot_indices: list, pivots: dict, shift_amounts: dict, new_tail: int, diff_count: int) -> dict:
        """피벗 인덱스를 Shift 오프셋에 맞게 갱신하고, 새 꼬리까지 추가 피벗을 생성합니다."""
        new_pivots = {}
        for p_idx in pivot_indices:
            shift = shift_amounts[p_idx]
            new_p_idx = p_idx + shift
            new_pivots[str(new_p_idx)] = pivots[str(p_idx)]

        # 새 꼬리까지의 추가 피벗 생성
        max_pivot = max(pivot_indices) if pivot_indices else 0
        next_pivot = (
            (max_pivot + shift_amounts.get(max_pivot, diff_count)) // settings.PIVOT_INTERVAL + 1
        ) * settings.PIVOT_INTERVAL
        while next_pivot < new_tail:
            row = await self._fetch_single(next_pivot)
            if row:
                # ✅ Boundary 양방향 저장
                last_row = await self._fetch_single(next_pivot + PAGE_SIZE - 1)
                new_pivots[str(next_pivot)] = {
                    "LCNS_NO": row.get("LCNS_NO", ""),
                    "LAST_LCNS_NO": last_row.get("LCNS_NO", "") if last_row else "",
                    "CHNG_DT": row.get("CHNG_DT", ""),
                    "BSSH_NM": row.get("BSSH_NM", "")
                }
            next_pivot += settings.PIVOT_INTERVAL

        return new_pivots

    async def scan_for_updates(self):
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        import time
        svc = self.service_id
        start_time = time.time()
        state = self.state_repo.load_state(self.service_id)

        if state["last_total_count"] == 0:
            logger.info(f"[{svc}] 최초 실행: 베이스라인 부트스트랩을 시작합니다...")
            state = await self.bootstrap()
            return []  # 부트스트랩 시에는 데이터를 가져오지 않고 베이스라인만 구축

        old_tail = state["last_total_count"]

        # find_true_tail 내부에서 Ping → 지수점프 → 이진탐색 → Gap스캔 전체 처리
        new_tail = await self.find_true_tail(known_tail=old_tail)

        if new_tail <= old_tail:
            elapsed = time.time() - start_time
            # ✅ Delete 은폐 감지: Tail이 같아도 Insert+Delete가 동시 발생했을 수 있음
            changed = await pivot_manager.sample_check(
                state.get("pivots", {}), self.api_client, svc
            )
            if changed:
                logger.warning(
                    f"[{svc}] ⚠️ [Delete 은폐 감지] Tail 변동 없으나 피벗 불일치! "
                    f"Insert+Delete 동시 발생 가능성. 다음 주기에 Tail 재탐색 예정."
                )
                # 은폐 감지 시 last_total_count를 -1 감소시켜 다음 주기에 강제 탐색 유도
                state["last_total_count"] = max(0, old_tail - 1)
                self.state_repo.save_state(self.service_id, state)
            else:
                logger.info(f"[{svc}] ✨ [소요: {elapsed:.2f}초] Tail 변동 없음. (tail: {old_tail:,}건)")
            return []

        diff_count = new_tail - old_tail
        logger.info(
            f"[{svc}] 🔍 [Delta 감지] Tail {old_tail:,} → {new_tail:,} (+{diff_count:,}건 신규 삽입)"
        )

        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])

        # Step 3: Pivot 검사 (Shift 오프셋 확인)
        shift_amounts = await self._compute_shift_offsets(pivots, pivot_indices, diff_count)

        # Step 4: 신규 데이터 다운로드
        new_data_rows = await self._download_new_rows(pivot_indices, shift_amounts, old_tail, new_tail, diff_count)

        # Step 5: 피벗 및 Tail 갱신 → DB 영속화
        new_pivots = await self._update_pivots(pivot_indices, pivots, shift_amounts, new_tail, diff_count)
        state["last_total_count"] = new_tail
        state["pivots"] = new_pivots
        self.state_repo.save_state(self.service_id, state)  # ← Tail 영속화

        return new_data_rows
