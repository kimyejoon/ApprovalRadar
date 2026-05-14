import time
import concurrent.futures
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.core.events import shutdown_event

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수

# total_count 필드가 신뢰 가능한 서비스 목록
# → 1회 API 호출로 정확한 Tail을 바로 얻을 수 있음 (페이지 스캔 불필요)
# I2859/I2500: total_count 신뢰 불가 (API 버그로 9 등 엉뚱한 값 반환)
# I2861: 음식점업소 인허가변경 - 이벤트 로그 append 구조로 total_count가 정확함
RELIABLE_TOTAL_COUNT_SERVICES = {"I2861"}


class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()

    # ─── 저수준 API 유틸리티 ──────────────────────────────────────────────────

    def _fetch_page(self, start: int, end: int) -> list:
        """
        [start, end] 범위의 레코드를 조회하여 row 리스트를 반환합니다.
        bulk 응답 지연을 고려해 30초 timeout 사용.
        - INFO-000: 정상 데이터 리스트 반환
        - INFO-200: 빈 페이지(데이터 없음) → [] 반환
        - 기타 오류: [] 반환
        """
        res = self.api_client.fetch_data(self.service_id, start, end, timeout=30)
        if not res or self.service_id not in res:
            return []
        block = res[self.service_id]
        code = block['RESULT']['CODE']
        if code == "INFO-000":
            return block.get('row', [])
        return []

    def _fetch_single(self, idx: int) -> dict | None:
        """특정 단일 인덱스 1건 조회 (피벗 확인용). 단건이므로 10초 timeout."""
        rows = self.api_client.fetch_data(self.service_id, idx, idx, timeout=10)
        if not rows or self.service_id not in rows:
            return None
        block = rows[self.service_id]
        code = block['RESULT']['CODE']
        if code == "INFO-000" and 'row' in block and block['row']:
            return block['row'][0]
        return None

    # ─── Tail 탐색 ────────────────────────────────────────────────────────────

    def find_true_tail(self, known_tail: int = 0) -> int:
        """
        서비스별 Tail 탐색 전략을 선택합니다:
        - RELIABLE_TOTAL_COUNT_SERVICES (I2861 등): total_count 1회 조회로 즉시 확보
        - I2859/I2500 등: 페이지 기반 스캔 (total_count 신뢰 불가)

        known_tail: DB에 저장된 이전 tail (0이면 최초 실행)
        """
        svc = self.service_id

        # ── 전략 A: total_count 직접 신뢰 서비스 ─────────────────────────────
        if svc in RELIABLE_TOTAL_COUNT_SERVICES:
            logger.info(f"[{svc}][Bootstrapper] 전체 데이터 건수 확인 중... (total_count 직접 조회)")
            res = self.api_client.fetch_data(svc, 1, 1, timeout=10)
            if res and svc in res:
                block = res[svc]
                code = block['RESULT']['CODE']
                if code in ("INFO-000", "INFO-200"):
                    total_count = int(block.get("TOTAL_COUNT", 0))
                    if total_count > 0:
                        logger.info(f"[{svc}][Bootstrapper] Tail 확정: {total_count:,}건 (total_count 직접)")
                        return total_count
            logger.warning(f"[{svc}][Bootstrapper] total_count 읽기 실패. 페이지 스캔으로 폴백합니다.")
            # 폴백: 아래 페이지 스캔으로 진행

        # ── 전략 B: 페이지 기반 스캔 (I2859, I2500 등) ───────────────────────
        logger.info(f"[{svc}][Bootstrapper] 전체 데이터 건수 확인 중... (페이지 기반 엔드-페이지 탐색)")

        # 알려진 Tail의 마지막 완전 페이지 경계부터 시작
        # 예: known_tail=22416 → 마지막 완전 페이지 = 22001 (22000+1)
        if known_tail > 0:
            page_start = ((known_tail - 1) // PAGE_SIZE) * PAGE_SIZE + 1
        else:
            page_start = 1

        # Step 1: 현재 페이지가 가득 찼는지 확인 (이전 tail이 여전히 유효한 페이지인지)
        # 이미 known_tail이 유효한 꼬리라면 → 변동 없음
        if known_tail > 0:
            rows = self._fetch_page(page_start, page_start + PAGE_SIZE - 1)
            if len(rows) == known_tail - (page_start - 1):
                # 마지막 페이지의 레코드 수가 이전과 동일 → tail 변화 없음
                logger.info(f"[{svc}][Bootstrapper] Tail 변동 없음: {known_tail:,}건 (저장된 페이지 그대로)")
                return known_tail

        # Step 2: 가득 찬 페이지를 따라 앞으로 점프
        while not shutdown_event.is_set():
            page_end = page_start + PAGE_SIZE - 1
            rows = self._fetch_page(page_start, page_end)
            row_count = len(rows)

            if row_count == 0:
                # 이 페이지에 데이터가 없음 → 이전 page_start - 1 이 Tail
                tail = page_start - 1
                logger.info(f"[{svc}][Bootstrapper] Tail 확정: {tail:,}건 (빈 페이지 도달)")
                return tail if tail > 0 else 0

            if row_count < PAGE_SIZE:
                # 마지막 페이지 발견: page_start - 1 + row_count
                tail = (page_start - 1) + row_count
                logger.info(f"[{svc}][Bootstrapper] Tail 확정: {tail:,}건 (마지막 페이지 {page_start}~{page_start+PAGE_SIZE-1}, {row_count}건 수록)")
                return tail

            # 가득 찬 페이지 → 다음 페이지로
            page_start += PAGE_SIZE

        return 0  # 종료 신호 수신

    # ─── 부트스트랩 ───────────────────────────────────────────────────────────

    def bootstrap(self):
        """처음부터 피벗을 생성합니다."""
        total_count = self.find_true_tail(known_tail=0)
        pivots = {}

        logger.info(f"[{self.service_id}][Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
        pivot_indices = list(range(settings.PIVOT_INTERVAL, total_count, settings.PIVOT_INTERVAL))

        # 피벗 병렬 조회 (피벗은 단건 조회이므로 _fetch_single 유지)
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.MAX_WORKERS) as executor:
            future_to_idx = {executor.submit(self._fetch_single, idx): idx for idx in pivot_indices}
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                row = future.result()
                if row:
                    pivots[str(idx)] = {
                        "LCNS_NO": row.get("LCNS_NO", ""),
                        "CHNG_DT": row.get("CHNG_DT", ""),
                        "BSSH_NM": row.get("BSSH_NM", "")
                    }

        state = {
            "last_total_count": total_count,
            "pivots": pivots
        }
        self.state_repo.save_state(self.service_id, state)
        logger.info(f"[{self.service_id}][Bootstrapper] 부트스트랩 완료! 총 {len(pivots)}개 피벗 색인 생성. (Tail: {total_count:,}건)")
        return state

    # ─── 델타 감지 ────────────────────────────────────────────────────────────

    def scan_for_updates(self):
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        svc = self.service_id
        start_time = time.time()
        state = self.state_repo.load_state(self.service_id)

        if state["last_total_count"] == 0:
            logger.info(f"[{svc}] 최초 실행: 베이스라인 부트스트랩을 시작합니다...")
            state = self.bootstrap()
            return []  # 부트스트랩 시에는 데이터를 가져오지 않고 베이스라인만 구축

        old_tail = state["last_total_count"]

        # ── Step 1: 빠른 Tail Ping ──────────────────────────────────────────
        # old_tail+1 부터 1000건을 요청 → 0건이면 변동 없음
        # 이 1회 호출로 "신규 레코드 존재 여부"를 확인
        ping_rows = self._fetch_page(old_tail + 1, old_tail + PAGE_SIZE)

        if not ping_rows:
            elapsed = time.time() - start_time
            logger.info(
                f"[{svc}] ✨ [소요: {elapsed:.2f}초] Tail 변동 없음. (현재 tail: {old_tail:,}건)"
            )
            return []

        # ── Step 2: 신규 Tail 탐색 ─────────────────────────────────────────
        # ping_rows가 있으므로 페이지 기반으로 새 꼬리를 찾음
        # known_tail=old_tail을 넘겨 마지막 알려진 페이지부터 탐색 재개
        new_tail = self.find_true_tail(known_tail=old_tail)

        if new_tail <= old_tail:
            # 이론상 발생하지 않지만 방어 코드
            elapsed = time.time() - start_time
            logger.info(f"[{svc}] ✨ [소요: {elapsed:.2f}초] Tail Ping 변동 없음. (현재 tail: {old_tail:,}건)")
            return []

        diff_count = new_tail - old_tail
        logger.info(
            f"[{svc}] 🔍 [Delta 감지] Tail {old_tail:,} → {new_tail:,} (+{diff_count:,}건 신규 삽입)"
        )

        # ── Step 3: Pivot 검사 (Shift 오프셋 확인) ─────────────────────────
        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])

        shift_amounts = {}  # pivot_idx -> shift_amount
        current_shift = 0

        logger.info(f"[{svc}] ⚙️ 피벗 {len(pivot_indices)}개 Shift 오프셋 보정 시작...")
        for p_idx in pivot_indices:
            old_data = pivots[str(p_idx)]
            found_offset = current_shift
            for offset in range(current_shift, diff_count + 1):
                row = self._fetch_single(p_idx + offset)
                if row and row.get("LCNS_NO") == old_data["LCNS_NO"] and row.get("CHNG_DT") == old_data["CHNG_DT"]:
                    found_offset = offset
                    break
            shift_amounts[p_idx] = found_offset
            current_shift = found_offset

        # ── Step 4: 신규 데이터 다운로드 ────────────────────────────────────
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
                rows = self._fetch_page(current_start, current_end)
                fetched_rows.extend(rows)
                current_start += PAGE_SIZE

            if fetched_rows:
                fetched_rows.sort(key=lambda x: x.get("CHNG_DT", ""), reverse=True)
                top_new = fetched_rows[:count]
                for r in top_new:
                    r["DB_INDEX_RANGE"] = f"{new_start}~{new_end}"
                new_data_rows.extend(top_new)

        # ── Step 5: 피벗 및 Tail 갱신 → DB 영속화 ──────────────────────────
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
            row = self._fetch_single(next_pivot)
            if row:
                new_pivots[str(next_pivot)] = {
                    "LCNS_NO": row.get("LCNS_NO", ""),
                    "CHNG_DT": row.get("CHNG_DT", ""),
                    "BSSH_NM": row.get("BSSH_NM", "")
                }
            next_pivot += settings.PIVOT_INTERVAL

        state["last_total_count"] = new_tail
        state["pivots"] = new_pivots
        self.state_repo.save_state(self.service_id, state)  # ← Tail 영속화

        return new_data_rows
