import asyncio
import random
import threading
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.core.events import shutdown_event
from app.services import pivot_manager

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수

# total_count 필드가 신뢰 가능한 서비스 목록
# → 1회 API 호출로 정확한 Tail을 바로 얻을 수 있음 (페이지 스캔 불필요)
# I2859: API 버그로 9 등 엉땅한 값 반환 (기존 알려진 문제)
# I2861: total_count=8 반환으로 신뢰 불가 확인 (2026-05-17 실증)
# → 향후 신뢰 가능한 서비스가 확인될 때만 이 set에 추가할 것.
RELIABLE_TOTAL_COUNT_SERVICES: set[str] = set()

# [Phase 3] Circuit Breaker 임계값
# diff_count가 이 값을 초과하면 API 한도 초과를 방지하기 위해 해당 주기를 즉시 중단하고
# 관리자에게 ALERT SSE를 발송한다. (Key 5개 × 1,000회 = 5,000회 한도 고려)
# .env CIRCUIT_BREAKER_THRESHOLD로 오버라이드 가능
CIRCUIT_BREAKER_THRESHOLD: int = int(__import__('os').getenv('CIRCUIT_BREAKER_THRESHOLD', '10000'))

# [B] Circuit Breaker 연속 발동 경고 임계값
# 타일 전진 대신 관리자 확인 요청만 수행 (데이터 손실 방지)
CIRCUIT_BREAKER_ALERT_AFTER = 3  # N회 연속 발동 시 강화 경고

# [C] bootstrap 동시성 제한: WAF DDoS 패턴 감지 방지
BOOTSTRAP_SEMAPHORE_LIMIT = 3  # 최대 동시 fetch_page 요청 수 (단일 Bootstrap 내부)

# [WAF Fix] 전역 Bootstrap 직렬화 Semaphore
# 서비스(I2859/I2861)의 Bootstrap 스레드가 동시에 실행되면
# 같은 IP에서 복수 asyncio 루프가 API를 동시에 호출 → WAF 차단 위험
# → Semaphore(1)로 한 번에 1개 서비스만 Bootstrap 실행하도록 직렬화
_GLOBAL_BOOTSTRAP_SEMAPHORE = threading.Semaphore(1)

# [Fix D] 기동 첫 주기 피벗 검증 완료 서비스 집합
# 서버 재시작 시에만 코드가 실행되는 모듈 레벨 상수이므로,
# 서버 재시작 후 각 서비스의 쳋 호출에만 피벗 stale 검증을 수행합니다.
# (DiffCrawlerEngine이 매 주기 새 인스턴스로 생성되마로 self._first_cycle은 매 주기 True로 리셋됨 → 버그)
_STARTUP_CHECK_DONE: set[str] = set()


class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()
        # 아래 카운터들은 scan_for_updates 시작 시 state에서 복원됨 (in-memory 초기화 대신)
        # [B] Circuit Breaker 연속 발동 카운터
        self._cb_consecutive_count: int = 0
        # [C] 빈 피벗 연속 주기 카운터: 일정 주기 초과 시 자동 re-bootstrap 트리거
        self._empty_pivot_cycles: int = 0
        # [D] _first_cycle은 모듈 레벨 _STARTUP_CHECK_DONE으로 관리 (인스턴스 변수 제거)
        # → DiffCrawlerEngine이 매 주기 새 인스턴스로 생성되어 self._first_cycle은 매번 True로 리셋됨
        # → 모듈 레벨 set(_STARTUP_CHECK_DONE)이 서버 프로세스 생명주기 동안 유지됨

    # ─── Bootstrap 독립 실행 ─────────────────────────────────────────────────

    async def _run_bootstrap_standalone(self) -> None:
        """
        [Bug-B Fix] Bootstrap 전용 독립 ApiClient 사용.

        run_scraper_for_service()의 async with ApiClient() 블록이
        scan_for_updates() 반환 직후 종료되어 api_client 세션이 닫힌다.
        threading.Thread에서 기존 api_client를 그대로 사용하면
        닫힌 세션으로 API 호출이 전부 실패한다.

        이 메서드는 독립적인 ApiClient를 새로 생성하여
        부트스트랩이 항상 정상 완료될 수 있도록 보장한다.

        [WAF Fix] _GLOBAL_BOOTSTRAP_SEMAPHORE로 직렬화:
        I2859/I2861이 동시에 Bootstrap을 실행하면 동일 IP에서
        복수의 asyncio 루프가 API를 동시 호출 → WAF 차단 위험.
        Semaphore(1)로 한 번에 1개 서비스만 Bootstrap 실행.

        실패 시: _bootstrapping 플래그를 DB에서 해제하여
        다음 주기에 재시도 가능하도록 복구한다.
        """
        logger.info(f"[{self.service_id}] 🔄 Bootstrap 스레드 시작 — 전역 Bootstrap Semaphore 대기 중...")
        acquired = _GLOBAL_BOOTSTRAP_SEMAPHORE.acquire(timeout=3600)  # 최대 1시간 대기
        if not acquired:
            logger.error(
                f"[{self.service_id}] ❌ Bootstrap Semaphore 대기 시간 초과 (1시간). "
                f"_bootstrapping 플래그 해제 후 다음 주기에 재시도."
            )
            try:
                state = self.state_repo.load_state(self.service_id)
                state.pop("_bootstrapping", None)
                self.state_repo.save_state(self.service_id, state)
            except Exception:
                pass
            return

        logger.info(f"[{self.service_id}] 🔄 Bootstrap 스레드 시작 (독립 ApiClient 사용, 직렬화 진행 중)")
        from app.clients.foodsafety_api import ApiClient as _ApiClient
        try:
            async with _ApiClient() as fresh_client:
                original_client = self.api_client
                self.api_client = fresh_client
                try:
                    await self.bootstrap()
                except Exception as e:
                    logger.error(
                        f"[{self.service_id}] ❌ Bootstrap 스레드 오류: {e}",
                        exc_info=True
                    )
                    # 실패 시 _bootstrapping 플래그 해제 → 다음 주기에 재시도 가능
                    try:
                        state = self.state_repo.load_state(self.service_id)
                        state.pop("_bootstrapping", None)
                        self.state_repo.save_state(self.service_id, state)
                        logger.warning(
                            f"[{self.service_id}] ⚠️ Bootstrap 실패 — _bootstrapping 플래그 해제. "
                            f"다음 주기에 재시도합니다."
                        )
                    except Exception as cleanup_err:
                        logger.error(f"[{self.service_id}] 플래그 해제 실패: {cleanup_err}")
                finally:
                    self.api_client = original_client
        finally:
            _GLOBAL_BOOTSTRAP_SEMAPHORE.release()
            logger.info(f"[{self.service_id}] 🔓 Bootstrap Semaphore 해제 — 다음 서비스 Bootstrap 가능")

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
                        # [A] 전략A 오응답 방어: total_count가 known_tail 대비 50% 이상 급감하면 신뢰 불가
                        # → 전략B(이진탐색)로 자동 fallback
                        if known_tail > 0 and total_count < known_tail * 0.5:
                            logger.warning(
                                f"[{svc}][전략A] ⚠️ total_count={total_count:,}이 "
                                f"known_tail={known_tail:,}의 50% 미만 — API 오응답 의심. "
                                f"전략B(이진탐색)로 자동 전환합니다."
                            )
                            # 전략B 진행 (아래 코드로 fall-through)
                        elif known_tail > 0 and total_count == known_tail:
                            logger.debug(f"[{svc}][전략A] 변동 없음: total_count={total_count:,} == known_tail={known_tail:,}")
                            logger.info(
                                f"[{svc}] ✔️ Tail 조사 완료: 현재 전체 {total_count:,}건 — 이번 주기 신규 인허가변동 없음."
                            )
                            return total_count
                        elif total_count > known_tail:
                            logger.info(
                                f"[{svc}] 🚨 Tail 조사 결과: 전체 {total_count:,}건 감지 → 이전({known_tail:,})보다 "
                                f"+{total_count - known_tail:,}건 신규 인허가변동 가능성 포착!"
                            )
                            return total_count
                        else:
                            logger.info(f"[{svc}][전략A] Tail 확정: {total_count:,}건 (total_count 직접)")
                            return total_count
            logger.warning(f"[{svc}][전략A] total_count 읽기 실패 또는 오응답, 페이지 탐색(전략B)으로 폴백")

        # ── 전략 B: 지수점프 + 이진탐색 + Gap허용 스캔 ───────────────────────
        logger.info(f"[{svc}][Bootstrapper] Tail 탐색 시작 (known_tail={known_tail:,})")

        # Step 1: Ping - known_tail 직후 확인 (빠른 경로). 전략A 성공 서비스는 여기 미도달.
        if known_tail > 0:
            ping = await self._fetch_page(known_tail + 1, known_tail + PAGE_SIZE)
            if not ping:
                logger.info(
                    f"[{svc}] ✔️ Tail 조사 완료: 현재 전체 {known_tail:,}건 — "
                    f"{known_tail+1:,}번 이후 데이터 없음 → 이번 주기 신규 발생 없음."
                )
                return known_tail
            logger.info(
                f"[{svc}] 📌 Ping: {known_tail+1:,}번 이후에 {len(ping)}건 데이터 감지 → 정확한 신규 건수 탐색 시작..."
            )


        # Step 0 (NEW): 소규모 데이터 Pre-check
        # 지수점프는 start_pos=PAGE_SIZE부터 시작하므로, 인덱스 1~(PAGE_SIZE-1) 구간을 탐지하지 못함.
        # known_tail=0일 때 첫 페이지 [1, PAGE_SIZE]를 선행 1회 조회하여 소규모 여부를 판단.
        if known_tail == 0:
            first_page = await self._fetch_page(1, PAGE_SIZE)
            if not first_page:
                # 인덱스 1부터 데이터 없음 → tail=0
                logger.info(f"[{svc}][전략B] Pre-check: 데이터 없음 (tail=0)")
                state = {"last_total_count": 0, "pivots": {}}
                self.state_repo.save_state(svc, state)
                return 0
            if len(first_page) < PAGE_SIZE:
                # 첫 페이지에 데이터가 PAGE_SIZE보다 적음 → 전체 데이터가 PAGE_SIZE 미만 (\uc18c규모)
                final_tail = len(first_page)
                logger.info(f"[{svc}][전략B] Pre-check: 소규모 데이터 감지 — tail={final_tail:,}건 (< PAGE_SIZE={PAGE_SIZE:,}). 지수점프 스킵.")
                logger.info(f"[{svc}][Bootstrapper] Tail 확정: {final_tail:,}")
                return final_tail
            # len == PAGE_SIZE: 정상 규모 → 기존 지수점프로 진행
            logger.debug(f"[{svc}][전략B] Pre-check: 정상 규모 ({PAGE_SIZE:,}건) → 지수점프 진행")

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

        # [Phase 2 + C] fetch_page 1회로 1,000건을 받아 rows[0]/rows[-1]로 Boundary 구성
        # [C] Semaphore로 최대 BOOTSTRAP_SEMAPHORE_LIMIT개 동시 요청 제한 (WAF DDoS 방지)
        semaphore = asyncio.Semaphore(BOOTSTRAP_SEMAPHORE_LIMIT)

        async def _fetch_pivot(idx: int):
            async with semaphore:
                rows = await self._fetch_page(idx, idx + PAGE_SIZE - 1)
            if rows:
                from app.services.pivot_manager import compute_page_fingerprint
                row = rows[0]
                last_row = rows[-1]
                return idx, {
                    "LCNS_NO": row.get("LCNS_NO", ""),
                    "CHNG_DT": row.get("CHNG_DT", ""),
                    "LAST_LCNS_NO": last_row.get("LCNS_NO", ""),
                    "LAST_CHNG_DT": last_row.get("CHNG_DT", ""),
                    "BSSH_NM": row.get("BSSH_NM", ""),
                    "fingerprint": compute_page_fingerprint(rows),
                }
            return idx, None

        results = await asyncio.gather(*[_fetch_pivot(idx) for idx in pivot_indices])
        for idx, pivot_data in results:
            if pivot_data:
                pivots[str(idx)] = pivot_data

        state = {
            "last_total_count": total_count,
            "pivots": pivots,
            "empty_pivot_cycles": 0,      # 재부트스트랩으로 카운터 초기화
            "cb_consecutive_count": 0,    # 재부트스트랩으로 카운터 초기화
        }
        self.state_repo.save_state(self.service_id, state)
        logger.info(f"[{self.service_id}][Bootstrapper] 부트스트랩 완료! 주 {len(pivots)}개 피벗 색인 생성. (Tail: {total_count:,}건)")

        # [Feedback-2 Fix] Bootstrap 완료 후 Tail 재조회
        # Bootstrap 진행 중(수 분 소요) 신규 변동분이 발생했을 경우
        # last_total_count가 실제 Tail보다 낮아 다음 주기에 정상 감지될 수 있도록 보장
        logger.info(f"[{self.service_id}] 🔍 Bootstrap 완료 후 Tail 재확인 중...")
        try:
            post_tail = await self.find_true_tail(known_tail=total_count)
            if post_tail > total_count:
                logger.info(
                    f"[{self.service_id}] 📌 Bootstrap 진행 중 {post_tail - total_count:,}건 추가 발생 감지 "
                    f"→ last_total_count를 {post_tail:,}으로 업데이트 (다음 주기 Delta 수집 보장)"
                )
                state["last_total_count"] = post_tail
                self.state_repo.save_state(self.service_id, state)
            else:
                logger.info(f"[{self.service_id}] ✅ Bootstrap 완료 후 Tail 변동 없음.")
        except Exception as e:
            logger.warning(f"[{self.service_id}] Bootstrap 후 Tail 재확인 실패 (무시): {e}")

        # ✅ [Fix 1] Bootstrap 완료 직후 피벗 즉시 재검증 (경량 모드)
        # 방금 생성한 피벗이므로 stale 가능성이 낮음 → 5%, 최대 5개 샘플만 확인
        # 기동 첫 주기(오래된 피벗)의 20% 전체 검증과 달리 빠르게 완료
        changed, _ = await pivot_manager.sample_check(
            state["pivots"], self.api_client, self.service_id,
            sample_ratio=0.05, max_samples=5
        )
        if changed:
            logger.warning(
                f"[{self.service_id}] ⚠️ Bootstrap 직후 피벗 불일치 감지 (Bootstrap 중 API 변동됨). "
                f"피벗 초기화 → 다음 주기에 Ping만으로 정상 탐색."
            )
            state["pivots"] = {}
            self.state_repo.save_state(self.service_id, state)
        else:
            logger.info(f"[{self.service_id}] ✅ Bootstrap 피벗 정합성 검증 완료.")
        self._empty_pivot_cycles = 0  # in-memory 동기화
        self._cb_consecutive_count = 0
        return state

    # ─── 델타 감지 ────────────────────────────────────────────────────────────

    async def _compute_shift_offsets(self, pivots: dict, pivot_indices: list, diff_count: int) -> dict:
        """
        [Phase 1] 피벗별 Shift 오프셋을 메모리 기반 청크 스캔으로 계산합니다.

        기존 방식(단건 fetch_single 루프)의 문제:
          - diff_count=500 시 API 500회 단건 호출 → 장기 다운타임 후 Key 고갈 위험

        개선 방식(청크 스캔):
          - 탐색 범위 [p_idx+current_shift, p_idx+diff_count]를 PAGE_SIZE(1,000건) 단위로
            fetch_page 1~2회 호출 후 메모리 리스트에서 선형 탐색
          - diff_count=500 시 피벗 1개당 API 1회 → 피벗 60개 전체 60회로 단축 (88% 절감)
          - Fallback: 피벗 레코드가 삭제 등으로 발견되지 않으면 current_shift 유지 후 다음 피벗 진행
        """
        shift_amounts = {}
        current_shift = 0

        logger.info(
            f"[{self.service_id}] ⏳ 피벗 Shift 분석 시작: 저장된 피벗 {len(pivot_indices)}개를 구간별로 스캔 "
            f"(diff_count={diff_count:,}, 포트 모드로 API 호출 최소화)"
        )
        for i, p_idx in enumerate(pivot_indices):
            old_data = pivots[str(p_idx)]
            # 레거시 문자열 포맷 및 신규 dict 포맷 모두 호환
            expected_lcns_no = old_data["LCNS_NO"] if isinstance(old_data, dict) else str(old_data)
            expected_chng_dt = old_data.get("CHNG_DT", "") if isinstance(old_data, dict) else ""

            found_offset = current_shift  # 미발견 시 Fallback: 현재 shift 유지
            found = False

            # [Feedback-1 Fix] 탐색 범위: 피벗 이전 구간도 포함
            # 삽입이 피벗 인덱스보다 앞 구간에서 발생하면 해당 피벗 레코드가 뒤로 밀림
            # → 기존: [p_idx+current_shift, p_idx+diff_count] (앞 구간 miss 가능)
            # → 수정: [max(prev_pivot_end, p_idx-diff_count), p_idx+diff_count]
            if i > 0:
                prev_p_idx = pivot_indices[i - 1]
                prev_shift = shift_amounts.get(prev_p_idx, current_shift)
                # 이전 피벗의 새 위치 이후부터 탐색 (중복 탐색 방지)
                search_start = max(prev_p_idx + prev_shift + 1, p_idx - diff_count)
            else:
                # 첫 피벗: diff_count만큼 앞으로 확장
                search_start = max(1, p_idx - diff_count)
            search_end = p_idx + diff_count
            current_search_pos = search_start

            logger.debug(
                f"[{self.service_id}] [청크 스캔] p_idx={p_idx:,} "
                f"탐색범위=[{search_start:,}~{search_end:,}] "
                f"(앞 구간 확장: {max(0, p_idx - search_start):,}건 추가 커버)"
            )

            while current_search_pos <= search_end and not found and not shutdown_event.is_set():
                chunk_end = min(current_search_pos + PAGE_SIZE - 1, search_end)
                rows = await self._fetch_page(current_search_pos, chunk_end)

                for i, row in enumerate(rows):
                    if (
                        row.get("LCNS_NO") == expected_lcns_no
                        and row.get("CHNG_DT") == expected_chng_dt
                    ):
                        # 실제 API 인덱스에서 p_idx를 빼면 offset
                        found_offset = (current_search_pos - p_idx) + i
                        found = True
                        break

                current_search_pos += PAGE_SIZE

            if not found:
                logger.warning(
                    f"[{self.service_id}] ⚠️ [청크 스캔] p_idx={p_idx:,} 피벗 레코드 미발견 "
                    f"(LCNS_NO={expected_lcns_no}). current_shift={current_shift} 유지 (Fallback)"
                )
            else:
                logger.debug(
                    f"[{self.service_id}] [청크 스캔] p_idx={p_idx:,} → offset={found_offset} 확정"
                )

            shift_amounts[p_idx] = found_offset
            current_shift = found_offset

        # 분석 완료: shift가 발생한 인덱스 범위 요약
        shifted_pivots = [(p_idx, shift_amounts[p_idx]) for p_idx in pivot_indices if shift_amounts[p_idx] > 0]
        if shifted_pivots:
            first_shifted_idx = shifted_pivots[0][0]
            logger.info(
                f"[{self.service_id}] 📍 피벗 분석 결과: "
                f"{first_shifted_idx:,}번 인덱스 앞에서 Shift 발생 → "
                f"해당 구간에 신규 데이터 삽입 가능성 확인"
            )
        else:
            logger.info(f"[{self.service_id}] 피벗 분석 결과: 모든 피벗 Shift=0 (데이터 타일단 나타남)")
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
                f"[{self.service_id}] 📥 피벗 조사 결과: "
                f"{seg_start:,}당~{seg_end:,}당 구간에 신규 데이터 {count}건 존재 가능성 포착!"
                f" (API 실제 요청 범위: {new_start:,}~{new_end:,})"
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
        """
        [Phase 2] 피벗 인덱스를 Shift 오프셋에 맞게 갱신하고, 새 꼬리까지 추가 피벗을 생성합니다.

        개선 사항:
          - 새 피벗 생성 시 _fetch_single × 2 (첫 행 + 마지막 행) →
            _fetch_page × 1 후 rows[0], rows[-1] 메모리 추출로 API 호출 50% 절감
        """
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
            # [Phase 2] fetch_page 1회로 1,000건을 통째로 가져와 메모리에서 첫/마지막 행 추출
            # 기존: _fetch_single(next_pivot) + _fetch_single(next_pivot + PAGE_SIZE - 1) = 2회
            # 개선: _fetch_page(next_pivot, next_pivot + PAGE_SIZE - 1) = 1회
            rows = await self._fetch_page(next_pivot, next_pivot + PAGE_SIZE - 1)
            if rows:
                from app.services.pivot_manager import compute_page_fingerprint
                row = rows[0]
                last_row = rows[-1]
                new_pivots[str(next_pivot)] = {
                    "LCNS_NO": row.get("LCNS_NO", ""),
                    "LAST_LCNS_NO": last_row.get("LCNS_NO", ""),
                    "CHNG_DT": row.get("CHNG_DT", ""),
                    "BSSH_NM": row.get("BSSH_NM", ""),
                    "fingerprint": compute_page_fingerprint(rows),  # ✅ 1,000건 전체 해시
                }
                logger.debug(
                    f"[{self.service_id}] [피벗 생성] idx={next_pivot:,} "
                    f"LCNS_NO={row.get('LCNS_NO','')} ~ {last_row.get('LCNS_NO','')}"
                )
            next_pivot += settings.PIVOT_INTERVAL

        return new_pivots

    async def scan_for_updates(self):
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        import time
        svc = self.service_id
        start_time = time.time()
        state = self.state_repo.load_state(self.service_id)

        # ✅ 카운터 영속 복원: 매 주기 새 인스턴스이므로 state에서 읽어온다
        self._empty_pivot_cycles = state.get("empty_pivot_cycles", 0)
        self._cb_consecutive_count = state.get("cb_consecutive_count", 0)

        # ✅ 피벗 재건 중이면 Ping Only 모드
        if state.get("_bootstrapping"):
            logger.info(
                f"[{svc}] 🔄 피벗 재건 백그라운드 진행 중... 이번 주기 Ping Only"
            )
            new_tail = await self.find_true_tail(known_tail=state["last_total_count"])
            if new_tail > state["last_total_count"]:
                logger.info(
                    f"[{svc}] 📌 피벗 재건 중 신규 {new_tail - state['last_total_count']:,}건 감지 "
                    f"→ 재건 완료 후 다음 주기에 수집"
                )
            return []

        if state["last_total_count"] == 0:
            logger.info(f"[{svc}] 최초 실행: 베이스라인 부트스트랩을 시작합니다...")
            state = await self.bootstrap()
            return []  # 부트스트랩 시에는 데이터를 가져오지 않고 베이스라인만 구축

        old_tail = state["last_total_count"]

        # ✅ [Fix D] 기동 첫 주기: 저장된 피벗 stale 여부 선제 검증
        # 서버 재시작 시 저장된 피벗이 수 시간~하루 이상 지난 값일 수 있음
        # → Ping 전에 먼저 피벗 검증 → stale이면 즉시 초기화 후 조기 종료
        # → 다음 주기는 pivots={}이므로 sample_check 스킵 → false Delete 은폐 alarm 차단
        # [Bug Fix] _STARTUP_CHECK_DONE (모듈 레벨 set) 사용:
        # DiffCrawlerEngine은 매 주기 새 인스턴스 → self._first_cycle은 매번 True로 리셋됨
        # → 모듈 레벨 set으로 서버 재시작 후 첫 주기에만 1회 검증 보장
        is_first_cycle = svc not in _STARTUP_CHECK_DONE
        if is_first_cycle:
            _STARTUP_CHECK_DONE.add(svc)
            if state.get("pivots"):
                logger.info(f"[{svc}] 🔍 기동 첫 주기: 저장 피벗 정합성 선제 검증 중...")
                startup_stale, shift_info = await pivot_manager.sample_check(
                    state["pivots"], self.api_client, svc, max_samples=9
                )
                if startup_stale:
                    shift_amount = shift_info.get("shift_amount")
                    insert_range = shift_info.get("insert_range")
                    # ✅ Shift 확정 시 기동 첫 주기에서도 즉시 수집
                    if shift_amount and shift_amount > 0 and insert_range:
                        ins_start, ins_end = insert_range
                        logger.info(
                            f"[{svc}] 📥 기동 첫 주기 즉시 수집: "
                            f"{ins_start:,}~{ins_end:,} 구간 ({shift_amount}건) — "
                            f"다음 주기를 기다리지 않고 즉시 변동분 확보"
                        )
                        immediate_rows = shift_info.get("new_rows") or []
                        if not immediate_rows:
                            cs = ins_start
                            while cs <= ins_end:
                                ce = min(cs + 1000 - 1, ins_end)
                                fetched = await self._fetch_page(cs, ce)
                                immediate_rows.extend(fetched)
                                cs += 1000
                        if immediate_rows:
                            logger.info(
                                f"[{svc}] ✅ 기동 즉시 수집 성공: {len(immediate_rows)}건 확보"
                            )
                            # 피벗 무효화 + 백그라운드 재건 시작 (플래그 설정)
                            state["pivots"] = {}
                            state["_bootstrapping"] = True
                            self.state_repo.save_state(self.service_id, state)
                            # [Bug-B Fix] 독립 ApiClient로 부트스트랩 실행
                            threading.Thread(
                                target=lambda: asyncio.run(self._run_bootstrap_standalone()),
                                daemon=True,
                                name=f"BootstrapThread-{svc}"
                            ).start()
                            logger.info(f"[{svc}] 🔄 피벗 재건 백그라운드 시작 (SSE/DB 저장과 병렬 실행)")
                            return immediate_rows  # scraper가 정상 처리
                    logger.warning(
                        f"[{svc}] ⚠️ 기동 시 피벗 stale 감지 (저장 후 API 변동됨). "
                        f"피벗 초기화 → 다음 주기부터 Ping만으로 정상 감지."
                    )
                    state["pivots"] = {}
                    self.state_repo.save_state(self.service_id, state)
                    return []
                else:
                    logger.info(f"[{svc}] ✅ 기동 피벗 정합성 확인됨. 정상 탐색 진행.")
        new_tail = await self.find_true_tail(known_tail=old_tail)

        if new_tail <= old_tail:
            elapsed = time.time() - start_time

            pivots = state.get("pivots", {})

            # pivots 있으면 Delete 은폐 감지 실행
            if pivots:
                # ✅ Delete 은폐 감지: Tail이 같아도 Insert+Delete가 동시 발생했을 수 있음
                # [Perf Fix] max_samples=9 제한: Delete 은폐는 극히 드문 시나리오 → 소량 샘플로 충분
                # I2861 기준: 38회 → 최대 9회 (기존 ~130초 → ~36초로 단축)
                changed, shift_info = await pivot_manager.sample_check(
                    pivots, self.api_client, svc, max_samples=9
                )
                if changed:
                    logger.warning(
                        f"[{svc}] ⚠️ [Delete 은폐 감지] Tail 변동 없으나 피벗 불일치! "
                        f"피벗 초기화 후 다음 주기에 정상 Delta 탐색으로 신규 변동분 수집 예정."
                    )

                    # ✅ Shift 진단으로 신규 데이터 즉시 수집
                    shift_amount = shift_info.get("shift_amount")
                    insert_range = shift_info.get("insert_range")
                    if shift_amount and shift_amount > 0 and insert_range:
                        ins_start, ins_end = insert_range
                        logger.info(
                            f"[{svc}] 📥 Shift값({shift_amount})을 토대로 즉시 신규변동분 수집: "
                            f"{ins_start:,} ~ {ins_end:,}번 구간 ({shift_amount}건)"
                        )
                        try:
                            immediate_rows = shift_info.get("new_rows") or []
                            if not immediate_rows:
                                cs = ins_start
                                while cs <= ins_end:
                                    ce = min(cs + 1000 - 1, ins_end)
                                    fetched = await self._fetch_page(cs, ce)
                                    immediate_rows.extend(fetched)
                                    cs += 1000
                            if immediate_rows:
                                logger.info(
                                    f"[{svc}] ✅ 즉시 수집 성공: {len(immediate_rows)}건 확보 — "
                                    f"기존 scraper 파이프라인으로 반환 (DB 저장 + SSE 발행)"
                                )
                                # 피벗 무효화 + 백그라운드 재건
                                state["pivots"] = {}
                                state["_bootstrapping"] = True
                                self.state_repo.save_state(self.service_id, state)
                                # [Bug-B Fix] 독립 ApiClient로 부트스트랩 실행
                                threading.Thread(
                                    target=lambda: asyncio.run(self._run_bootstrap_standalone()),
                                    daemon=True,
                                    name=f"BootstrapThread-{svc}"
                                ).start()
                                logger.info(f"[{svc}] 🔄 피벗 재건 백그라운드 시작")
                                return immediate_rows
                            else:
                                logger.warning(f"[{svc}] 즉시 수집: {ins_start:,}~{ins_end:,} 응답 없음")
                        except Exception as e:
                            logger.warning(f"[{svc}] 즉시 수집 실패 (다음 주기 재시도): {e}")

                    state["pivots"] = {}
                    self.state_repo.save_state(self.service_id, state)
                    return []

            logger.info(
                f"[{svc}] ✔️ 이번 주기 신규 변동없음. (tail: {old_tail:,}건) "
                f"[소요: {time.time() - start_time:.1f}초]"
            )
            # ✅ 피벗 없음 → 다음 주기 즉시 재부트스트랩 (1주기 후)
            # - 피벗이 비어있으면 Delete 은폐 감지 불가 → 최대한 빠르게 복원
            # - MAX_EMPTY=1: Tail 변동 없음 확인 직후 즉시 재부트스트랩 실행
            if not pivots:
                self._empty_pivot_cycles += 1
                MAX_EMPTY = 1
                logger.info(
                    f"[{svc}] 📋 피벗 없음 (Ping Only 모드) → "
                    f"{'즉시 재부트스트랩 시작!' if self._empty_pivot_cycles >= MAX_EMPTY else '다음 주기 재부트스트랩 예정'}"
                )
                # 카운터 영속 저장
                state["empty_pivot_cycles"] = self._empty_pivot_cycles
                self.state_repo.save_state(self.service_id, state)
                if self._empty_pivot_cycles >= MAX_EMPTY:
                    logger.warning(f"[{svc}] 🔄 피벗 재건 백그라운드 시작 → Delete 은폐 감지 복원 중...")
                    state["_bootstrapping"] = True
                    self.state_repo.save_state(self.service_id, state)
                    # [Bug-B Fix] 독립 ApiClient로 부트스트랩 실행
                    threading.Thread(
                        target=lambda: asyncio.run(self._run_bootstrap_standalone()),
                        daemon=True,
                        name=f"BootstrapThread-{self.service_id}"
                    ).start()
            else:
                if self._empty_pivot_cycles != 0:
                    self._empty_pivot_cycles = 0
                    state["empty_pivot_cycles"] = 0
                    self.state_repo.save_state(self.service_id, state)
            return []


        diff_count = new_tail - old_tail

        # ── [Phase 3] Circuit Breaker ────────────────────────────────────────────
        # diff_count가 임계값 초과 시 API 한도 보호를 위해 이번 주기를 안전하게 중단한다.
        # [B] 3회 연속 발동 시 자가 복구: last_total_count = new_tail 강제 업데이트
        if diff_count > CIRCUIT_BREAKER_THRESHOLD:
            svc_name = {
                "I2859": "식품업소 인허가변경",
                "I2861": "음식점업소 인허가변경",
            }.get(svc, svc)
            self._cb_consecutive_count += 1
            logger.error(
                f"[{svc}] 🚨 [Circuit Breaker #{self._cb_consecutive_count}] diff_count={diff_count:,}건이 "
                f"임계값({CIRCUIT_BREAKER_THRESHOLD:,})을 초과! "
                f"API 한도 초과 방지를 위해 이번 주기를 강제 중단합니다."
            )
            try:
                from app.core.events import broadcaster
                import json
                alert_msg = json.dumps({
                    "type": "ALERT",
                    "message": (
                        f"[Circuit Breaker #{self._cb_consecutive_count}] {svc_name} 변동분 {diff_count:,}건 감지 — "
                        f"API 한도 초과 위험으로 이번 주기를 중단했습니다."
                        + (f" ({CIRCUIT_BREAKER_AUTO_RECOVERY_AFTER}회 연속 발동 시 자동 복구를 시도합니다.)" if self._cb_consecutive_count < CIRCUIT_BREAKER_AUTO_RECOVERY_AFTER else "")
                    )
                }, ensure_ascii=False)
                broadcaster.broadcast_sync(alert_msg)
            except Exception:
                pass

            # [A-Tier Fix] CB 연속 발동 시: Tail 강제 전진(데이터 손실) 대신 관리자 확인 요구
            if self._cb_consecutive_count >= CIRCUIT_BREAKER_ALERT_AFTER:
                logger.critical(
                    f"[{svc}] 🚨 [CB {self._cb_consecutive_count}회 연속] "
                    f"diff_count={diff_count:,}건 — 자동 복구 중단. "
                    f"관리자 확인 필요: API 재정렬 가능성 또는 실제 대량 신규 등록. "
                    f"크롤링 주기를 늘리거나 .env CIRCUIT_BREAKER_THRESHOLD를 조정하세요."
                )
                try:
                    from app.core.events import broadcaster
                    import json
                    alert_msg = json.dumps({
                        "type": "ALERT",
                        "message": (
                            f"[CB {self._cb_consecutive_count}회 연속] {svc_name} {diff_count:,}건 감지 — "
                            f"자동 복구 중단됨. 관리자 확인 필요."
                        )
                    }, ensure_ascii=False)
                    broadcaster.broadcast_sync(alert_msg)
                except Exception:
                    pass
            # Tail 전진 없음 → 다음 주기에 동일한 diff_count로 재평가
            state["cb_consecutive_count"] = self._cb_consecutive_count
            self.state_repo.save_state(self.service_id, state)
            return []
        # ────────────────────────────────────────────────────────────────────────
        # Circuit Breaker 미발동 시 연속 카운터 리셋
        self._cb_consecutive_count = 0

        logger.info(
            f"[{svc}] 🔍 [Delta 감지] Tail {old_tail:,} → {new_tail:,} (+{diff_count:,}건)"
            f" — 신규 인허가변동 {diff_count:,}건 포착! 구간 분석 시작..."
        )

        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])
        if pivot_indices:
            logger.info(
                f"[{svc}] 피벗 {len(pivot_indices)}개 구성됨 — "
                f"({pivot_indices[0]:,} ~ {pivot_indices[-1]:,} 범위를 {len(pivot_indices)}구간으로 분할)"
            )
        else:
            logger.warning(
                f"[{svc}] 피벗 없음! Tail만으로 신규 구간 플립을 특정할 수 없음. "
                f"Tail 다운로드만 진행."
            )

        # Step 3: Pivot 검사 (Shift 오프셋 확인)
        shift_amounts = await self._compute_shift_offsets(pivots, pivot_indices, diff_count)

        # Step 4: 신규 데이터 다운로드
        new_data_rows = await self._download_new_rows(pivot_indices, shift_amounts, old_tail, new_tail, diff_count)

        # Step 5: 피벗 및 Tail 갱신 → DB 영속화
        new_pivots = await self._update_pivots(pivot_indices, pivots, shift_amounts, new_tail, diff_count)
        state["last_total_count"] = new_tail
        state["pivots"] = new_pivots
        self.state_repo.save_state(self.service_id, state)  # ← Tail 영속화

        logger.info(
            f"[{svc}] 💾 신규 변동분 {len(new_data_rows):,}건 수집 완료. (tail {old_tail:,} → {new_tail:,})"
        )
        return new_data_rows
