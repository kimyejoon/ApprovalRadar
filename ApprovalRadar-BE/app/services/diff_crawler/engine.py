import asyncio
import random
import time
import threading
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.services.rolling_scanner import RollingScanner

# 분리한 모듈 임포트
from app.services.diff_crawler import circuit_breaker
from app.services.diff_crawler import bootstrapper
from app.services.diff_crawler import delta_detector

PAGE_SIZE = 1000
DIRECT_COLLECT_THRESHOLD = 10


class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()
        
        # 카운터 메모리 복원용 임시 변수
        self._cb_consecutive_count: int = 0
        self._empty_pivot_cycles: int = 0
        self._reshuffled: bool = False

    async def _fetch_page(self, start: int, end: int) -> list:
        """[start, end] 범위의 레코드를 비동기 조회하여 Jitter를 적용한 후 반환합니다."""
        res = await self.api_client.fetch_data(self.service_id, start, end, timeout=30)
        await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
        if not res or self.service_id not in res:
            return []
        block = res[self.service_id]
        if block['RESULT']['CODE'] == "INFO-000":
            return block.get('row', [])
        return []

    async def _fetch_single(self, idx: int) -> dict | None:
        """특정 단일 인덱스 1건 비동기 조회 및 Jitter 적용."""
        rows = await self.api_client.fetch_data(self.service_id, idx, idx, timeout=10)
        await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))
        if not rows or self.service_id not in rows:
            return None
        block = rows[self.service_id]
        if block['RESULT']['CODE'] == "INFO-000" and 'row' in block and block['row']:
            return block['row'][0]
        return None

    async def find_true_tail(self, known_tail: int = 0) -> int:
        """실제 데이터 끝(Tail) 위치를 정확하게 탐색합니다."""
        return await bootstrapper.find_true_tail(self, known_tail)

    async def _run_bootstrap_standalone(self) -> None:
        """비동기 백그라운드 스레드에서 안전한 Bootstrap 실행을 수행합니다."""
        await bootstrapper.run_bootstrap_standalone(self)

    async def bootstrap(self) -> dict:
        """처음부터 피벗을 생성하고 정합성을 검증합니다."""
        return await bootstrapper.bootstrap(self)

    async def scan_for_updates(self) -> list:
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        svc = self.service_id
        start_time = time.time()
        state = self.state_repo.load_state(svc)

        self._empty_pivot_cycles = state.get("empty_pivot_cycles", 0)
        self._cb_consecutive_count = state.get("cb_consecutive_count", 0)

        # 피벗 재건 중이면 Ping Only 모드
        if state.get("_bootstrapping"):
            logger.info(f"[{svc}] 🔄 피벗 재건 백그라운드 진행 중... 이번 주기 Ping Only")
            new_tail = await self.find_true_tail(known_tail=state["last_total_count"])
            if new_tail > state["last_total_count"]:
                logger.info(
                    f"[{svc}] 📌 피벗 재건 중 신규 {new_tail - state['last_total_count']:,}건 감지 "
                    f"→ 재건 완료 후 다음 주기에 수집"
                )
            return []

        if state.get("last_total_count", 0) == 0:
            logger.info(f"[{svc}] 최초 실행: 베이스라인 부트스트랩을 시작합니다...")
            state = await self.bootstrap()
            return []

        old_tail = state["last_total_count"]
        self._reshuffled = False
        new_tail = await self.find_true_tail(known_tail=old_tail)

        # API 재정렬 감지 시 즉시 백그라운드 재부트스트랩 트리거
        if self._reshuffled:
            logger.warning(
                f"[{svc}] 🔄 API 재정렬 감지 (known_tail 역방향 검증 실패) "
                f"→ Tail={new_tail:,}으로 갱신 후 즉시 재부트스트랩"
            )
            state["last_total_count"] = new_tail
            state["pivots"] = {}
            state["_bootstrapping"] = True
            self.state_repo.save_state(svc, state)

            def _bg_bootstrap():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._run_bootstrap_standalone())
                finally:
                    loop.close()
            threading.Thread(target=_bg_bootstrap, daemon=True, name=f"reshuffle-bootstrap-{svc}").start()
            return []

        if new_tail <= old_tail:
            # 변동 없음 -> Rolling Scan 수행
            from app.core.config import get_rolling_pages_for_service
            svc_pages = get_rolling_pages_for_service(svc)
            scanner = RollingScanner(self.api_client, svc, self.state_repo)

            async def _flush_rolling_rows(rows: list):
                from scraper import run_scraper_for_service_with_rows
                await run_scraper_for_service_with_rows(svc, rows, collected_by="rolling_scan")

            logger.info(f"[{svc}] 🎯 Rolling Scan 할당: {svc_pages}p")
            rolling_new_rows = await scanner.scan_cycle(
                pages_per_cycle=svc_pages,
                flush_callback=_flush_rolling_rows
            )

            # Delete 은폐 감지: Tail이 동일해도 중간 레코드의 Insert+Delete가 동시 발생 가능성
            from app.services import pivot_manager
            changed, _ = await pivot_manager.sample_check(
                state.get("pivots", {}), self.api_client, svc,
                sample_ratio=0.2
            )
            if changed:
                logger.warning(
                    f"[{svc}] ⚠️ [Delete 은폐 감지] Tail 변동 없으나 피벗 불일치! "
                    f"Insert+Delete 동시 발생 가능성. 다음 주기에 Tail 재탐색 예정."
                )
                state["last_total_count"] = max(0, old_tail - 1)
                self.state_repo.save_state(svc, state)

            if rolling_new_rows:
                logger.info(f"[{svc}] 📥 Rolling Scan 신규 {len(rolling_new_rows)}건 발견 → 파이프라인 반환")
                return rolling_new_rows

            elapsed = time.time() - start_time
            logger.info(f"[{svc}] ✔️ 이번 주기 신규 변동없음. (tail: {old_tail:,}건) [소요: {elapsed:.1f}초]")
            return []

        diff_count = new_tail - old_tail

        # Circuit Breaker 발동 여부 검증
        cb_triggered, self._cb_consecutive_count = circuit_breaker.check_circuit_breaker(
            svc, diff_count, state, self._cb_consecutive_count
        )
        if cb_triggered:
            state["cb_consecutive_count"] = self._cb_consecutive_count
            self.state_repo.save_state(svc, state)
            return []

        self._cb_consecutive_count = 0
        state["cb_consecutive_count"] = 0

        logger.info(
            f"[{svc}] 🔍 [Delta 감지] Tail {old_tail:,} → {new_tail:,} (+{diff_count:,}건) 구간 분석 시작..."
        )

        # 소량 변동인 경우 바로 Tail 직접 수집
        if diff_count <= DIRECT_COLLECT_THRESHOLD:
            logger.info(f"[{svc}] ⚡ diff_count={diff_count:,}건 ≤ {DIRECT_COLLECT_THRESHOLD} → Tail 직접 수집")
            new_data_rows = []
            fetch_start = old_tail + 1
            while fetch_start <= new_tail:
                fetch_end = min(fetch_start + PAGE_SIZE - 1, new_tail)
                rows = await self._fetch_page(fetch_start, fetch_end)
                new_data_rows.extend(rows)
                fetch_start += PAGE_SIZE

            state["last_total_count"] = new_tail
            self.state_repo.save_state(svc, state)
            logger.info(f"[{svc}] 💾 Tail 직접 수집 완료: {len(new_data_rows):,}건")
            return new_data_rows

        # 대량 변동인 경우 피벗 Shift 분석 경로 실행
        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])
        if not pivot_indices:
            logger.warning(f"[{svc}] 피벗 없음! Tail 다운로드만 진행.")

        shift_amounts = await delta_detector.compute_shift_offsets(self, pivots, pivot_indices, diff_count)

        if shift_amounts is None:
            logger.warning(f"[{svc}] 🔄 전체 재정렬 감지 → Tail 업데이트 후 재부트스트랩 트리거")
            state["last_total_count"] = new_tail
            state["pivots"] = {}
            state["_bootstrapping"] = True
            self.state_repo.save_state(svc, state)

            def _bg_bootstrap():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._run_bootstrap_standalone())
                finally:
                    loop.close()
            threading.Thread(target=_bg_bootstrap, daemon=True, name=f"rebootstrap-{svc}").start()
            return []

        new_data_rows = await delta_detector.download_new_rows(
            self, pivot_indices, shift_amounts, old_tail, new_tail, diff_count
        )
        new_pivots = await delta_detector.update_pivots(
            self, pivot_indices, pivots, shift_amounts, new_tail, diff_count
        )

        state["last_total_count"] = new_tail
        state["pivots"] = new_pivots
        self.state_repo.save_state(svc, state)

        logger.info(f"[{svc}] 💾 신규 변동분 {len(new_data_rows):,}건 수집 완료. (tail {old_tail:,} → {new_tail:,})")
        return new_data_rows
