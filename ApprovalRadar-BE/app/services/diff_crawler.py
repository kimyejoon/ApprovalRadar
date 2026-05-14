import time
import concurrent.futures
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.core.events import shutdown_event

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수


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
        페이지 기반으로 실제 마지막 레코드 번호(Tail)를 탐색합니다.

        알고리즘:
        1. known_tail이 있으면 해당 페이지 경계부터 시작 (이미 알려진 꼬리 활용)
        2. 1000건씩 점프하며 "다음 페이지가 존재하는가?"를 확인
        3. 빈 페이지가 나타나면 → 직전 페이지의 실제 마지막 인덱스 = Tail

        특성:
        - API TOTAL_COUNT 필드 사용 안 함 (신뢰 불가)
        - WAF 친화적: 1000건 단위 벌크 요청만 사용 (개별 건 조회 없음)
        - DB 저장 tail에서 재개하므로 라이프사이클 간 중복 탐색 없음
        """
        logger.info("[Bootstrapper] 전체 데이터 건수 확인 중... (페이지 기반 엔드-페이지 탐색)")

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
                logger.info(f"[Bootstrapper] 전체 데이터 건수 확인 완료: {known_tail:,}건 (변동 없음)")
                return known_tail

        # Step 2: 가득 찬 페이지를 따라 앞으로 점프
        while not shutdown_event.is_set():
            page_end = page_start + PAGE_SIZE - 1
            rows = self._fetch_page(page_start, page_end)
            row_count = len(rows)

            if row_count == 0:
                # 이 페이지에 데이터가 없음 → 이전 page_start - 1 이 Tail
                # (직전 페이지가 가득 찼을 때 발생)
                tail = page_start - 1
                logger.info(f"[Bootstrapper] 전체 데이터 건수 확인 완료: {tail:,}건")
                return tail if tail > 0 else 0

            if row_count < PAGE_SIZE:
                # 마지막 페이지 발견: page_start - 1 + row_count
                tail = (page_start - 1) + row_count
                logger.info(f"[Bootstrapper] 전체 데이터 건수 확인 완료: {tail:,}건")
                return tail

            # 가득 찬 페이지 → 다음 페이지로
            page_start += PAGE_SIZE

        return 0  # 종료 신호 수신

    # ─── 부트스트랩 ───────────────────────────────────────────────────────────

    def bootstrap(self):
        """처음부터 피벗을 생성합니다."""
        total_count = self.find_true_tail(known_tail=0)
        pivots = {}

        logger.info(f"[Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
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
        logger.info(f"[Bootstrapper] 부트스트랩 완료! 총 {len(pivots)}개의 피벗 색인 생성됨.")
        return state

    # ─── 델타 감지 ────────────────────────────────────────────────────────────

    def scan_for_updates(self):
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        start_time = time.time()
        state = self.state_repo.load_state(self.service_id)

        if state["last_total_count"] == 0:
            logger.info("최초 실행: 베이스라인 부트스트랩을 시작합니다...")
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
                f"✨ [소요시간: {elapsed:.2f}초] "
                f"새로운 데이터가 감지되지 않았습니다. (현재 전체 데이터: {old_tail:,}건)"
            )
            return []

        # ── Step 2: 신규 Tail 탐색 ─────────────────────────────────────────
        # ping_rows가 있으므로 페이지 기반으로 새 꼬리를 찾음
        # known_tail=old_tail을 넘겨 마지막 알려진 페이지부터 탐색 재개
        new_tail = self.find_true_tail(known_tail=old_tail)

        if new_tail <= old_tail:
            # 이론상 발생하지 않지만 방어 코드
            elapsed = time.time() - start_time
            logger.info(f"✨ [소요시간: {elapsed:.2f}초] 변동 없음 확인. (현재 전체 데이터: {old_tail:,}건)")
            return []

        diff_count = new_tail - old_tail
        logger.info(
            f"🔍 [Tail 탐색] 인덱스가 {old_tail:,}에서 {new_tail:,}로 증가했습니다. "
            f"(총 {diff_count:,}건의 신규 삽입 감지)"
        )

        # ── Step 3: Pivot 검사 (Shift 오프셋 확인) ─────────────────────────
        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])

        shift_amounts = {}  # pivot_idx -> shift_amount
        current_shift = 0

        logger.info(f"⚙️ 총 {len(pivot_indices)}개의 피벗 지점에서 Shift 오프셋 보정을 시작합니다...")
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
