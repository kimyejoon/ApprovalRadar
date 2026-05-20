import asyncio
import time
import threading
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger
from app.services.rolling_scanner import RollingScanner

from app.services.crawler_constants import PAGE_SIZE, CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_ALERT_AFTER
from app.services.api_utils import fetch_page
from app.services.tail_explorer import TailExplorer
from app.services.pivot_analyzer import PivotAnalyzer
from app.services.diff_bootstrapper import DiffBootstrapper

class DiffCrawlerEngine:
    """
    DiffCrawlerEngine acts as a facade, orchestrating the differential crawling 
    process using specialized helper classes.
    """
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()
        
        self.tail_explorer = TailExplorer(self.api_client, self.service_id, self.state_repo)
        self.pivot_analyzer = PivotAnalyzer(self.api_client, self.service_id)
        self.diff_bootstrapper = DiffBootstrapper(self.api_client, self.service_id, self.state_repo)
        
        self._cb_consecutive_count: int = 0
        self._empty_pivot_cycles: int = 0
        self._reshuffled: bool = False

    async def _download_new_rows(self, pivot_indices: list, shift_amounts: dict, old_tail: int, new_tail: int, diff_count: int) -> list:
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
                rows = await fetch_page(self.api_client, self.service_id, current_start, current_end)
                fetched_rows.extend(rows)
                current_start += PAGE_SIZE

            if fetched_rows:
                fetched_rows.sort(key=lambda x: x.get("CHNG_DT", ""), reverse=True)
                top_new = fetched_rows[:count]
                for r in top_new:
                    r["DB_INDEX_RANGE"] = f"{new_start}~{new_end}"
                new_data_rows.extend(top_new)

        return new_data_rows

    async def scan_for_updates(self):
        svc = self.service_id
        start_time = time.time()
        state = self.state_repo.load_state(self.service_id)

        self._empty_pivot_cycles = state.get("empty_pivot_cycles", 0)
        self._cb_consecutive_count = state.get("cb_consecutive_count", 0)

        if state.get("_bootstrapping"):
            logger.info(f"[{svc}] 🔄 피벗 재건 백그라운드 진행 중... 이번 주기 Ping Only")
            new_tail = await self.tail_explorer.find_true_tail(known_tail=state["last_total_count"])
            if new_tail > state["last_total_count"]:
                logger.info(f"[{svc}] 📌 피벗 재건 중 신규 {new_tail - state['last_total_count']:,}건 감지 → 재건 완료 후 다음 주기에 수집")
            return []

        if state["last_total_count"] == 0:
            logger.info(f"[{svc}] 최초 실행: 베이스라인 부트스트랩을 시작합니다...")
            state = await self.diff_bootstrapper.bootstrap()
            return []

        old_tail = state["last_total_count"]

        self.tail_explorer.reshuffled = False
        new_tail = await self.tail_explorer.find_true_tail(known_tail=old_tail)

        if self.tail_explorer.reshuffled:
            logger.warning(f"[{svc}] 🔄 API 재정렬 감지 (known_tail 역방향 검증 실패) → Tail={new_tail:,}으로 갱신 후 즉시 재부트스트랩")
            state["last_total_count"] = new_tail
            state["pivots"] = {}
            state["_bootstrapping"] = True
            self.state_repo.save_state(self.service_id, state)

            def _bg_bootstrap():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.diff_bootstrapper._run_bootstrap_standalone())
                finally:
                    loop.close()
            threading.Thread(target=_bg_bootstrap, daemon=True, name=f"reshuffle-bootstrap-{svc}").start()
            logger.info(f"[{svc}] 🔄 백그라운드 재부트스트랩 시작됨 (API 재정렬 대응)")
            return []

        if new_tail <= old_tail:
            elapsed = time.time() - start_time
            from app.core.config import get_rolling_pages_for_service
            svc_pages = get_rolling_pages_for_service(svc)
            scanner = RollingScanner(self.api_client, svc, self.state_repo)

            async def _flush_rolling_rows(rows: list):
                from scraper import run_scraper_for_service_with_rows
                await run_scraper_for_service_with_rows(svc, rows, collected_by="rolling_scan")

            logger.info(f"[{svc}] 🎯 Rolling Scan 할당: {svc_pages}p (총 {settings.ROLLING_SCAN_PAGES_PER_CYCLE}p 중 비례배분)")
            rolling_new_rows = await scanner.scan_cycle(pages_per_cycle=svc_pages, flush_callback=_flush_rolling_rows)

            if rolling_new_rows:
                logger.info(f"[{svc}] 📥 Rolling Scan 신규 {len(rolling_new_rows)}건 발견 → scraper 파이프라인으로 반환 (DB 저장 + SSE 발행)")
                return rolling_new_rows

            elapsed = time.time() - start_time
            logger.info(f"[{svc}] ✔️ 이번 주기 신규 변동없음. (tail: {old_tail:,}건) [소요: {elapsed:.1f}초]")
            return []

        diff_count = new_tail - old_tail

        if diff_count > CIRCUIT_BREAKER_THRESHOLD:
            svc_name = {"I2859": "식품업소 인허가변경", "I2861": "음식점업소 인허가변경"}.get(svc, svc)
            self._cb_consecutive_count += 1
            logger.error(f"[{svc}] 🚨 [Circuit Breaker #{self._cb_consecutive_count}] diff_count={diff_count:,}건이 임계값({CIRCUIT_BREAKER_THRESHOLD:,})을 초과! API 한도 초과 방지를 위해 이번 주기를 강제 중단합니다.")
            try:
                from app.core.events import broadcaster
                import json
                alert_msg = json.dumps({
                    "type": "ALERT",
                    "message": (
                        f"[Circuit Breaker #{self._cb_consecutive_count}] {svc_name} 변동분 {diff_count:,}건 감지 — API 한도 초과 위험으로 이번 주기를 중단했습니다."
                        + (f" ({CIRCUIT_BREAKER_ALERT_AFTER}회 연속 발동 시 강화 경고가 발송됩니다.)" if self._cb_consecutive_count < CIRCUIT_BREAKER_ALERT_AFTER else "")
                    )
                }, ensure_ascii=False)
                broadcaster.broadcast_sync(alert_msg)
            except Exception:
                pass

            if self._cb_consecutive_count >= CIRCUIT_BREAKER_ALERT_AFTER:
                logger.critical(f"[{svc}] 🚨 [CB {self._cb_consecutive_count}회 연속] diff_count={diff_count:,}건 — 자동 복구 중단. 관리자 확인 필요: API 재정렬 가능성 또는 실제 대량 신규 등록. 크롤링 주기를 늘리거나 .env CIRCUIT_BREAKER_THRESHOLD를 조정하세요.")
                try:
                    from app.core.events import broadcaster
                    import json
                    alert_msg = json.dumps({
                        "type": "ALERT",
                        "message": f"[CB {self._cb_consecutive_count}회 연속] {svc_name} {diff_count:,}건 감지 — 자동 복구 중단됨. 관리자 확인 필요."
                    }, ensure_ascii=False)
                    broadcaster.broadcast_sync(alert_msg)
                except Exception:
                    pass
            state["cb_consecutive_count"] = self._cb_consecutive_count
            self.state_repo.save_state(self.service_id, state)
            return []

        self._cb_consecutive_count = 0
        logger.info(f"[{svc}] 🔍 [Delta 감지] Tail {old_tail:,} → {new_tail:,} (+{diff_count:,}건) — 신규 인허가변동 {diff_count:,}건 포착! 구간 분석 시작...")

        DIRECT_COLLECT_THRESHOLD = 10
        if diff_count <= DIRECT_COLLECT_THRESHOLD:
            logger.info(f"[{svc}] ⚡ diff_count={diff_count:,}건 <= {DIRECT_COLLECT_THRESHOLD} → Tail 직접 수집 (피벗 Shift 분석 스킵)")
            new_data_rows = []
            fetch_start = old_tail + 1
            while fetch_start <= new_tail:
                fetch_end = min(fetch_start + PAGE_SIZE - 1, new_tail)
                rows = await fetch_page(self.api_client, self.service_id, fetch_start, fetch_end)
                new_data_rows.extend(rows)
                fetch_start += PAGE_SIZE

            state["last_total_count"] = new_tail
            self.state_repo.save_state(self.service_id, state)
            logger.info(f"[{svc}] 💾 Tail 직접 수집 완료: {len(new_data_rows):,}건 (tail {old_tail:,} → {new_tail:,})")
            return new_data_rows

        pivots = state["pivots"]
        pivot_indices = sorted([int(k) for k in pivots.keys()])
        if pivot_indices:
            logger.info(f"[{svc}] 피벗 {len(pivot_indices)}개 구성됨 — ({pivot_indices[0]:,} ~ {pivot_indices[-1]:,} 범위를 {len(pivot_indices)}구간으로 분할)")
        else:
            logger.warning(f"[{svc}] 피벗 없음! Tail만으로 신규 구간을 특정할 수 없음. Tail 다운로드만 진행.")

        shift_amounts = await self.pivot_analyzer.compute_shift_offsets(pivots, pivot_indices, diff_count)

        if shift_amounts is None:
            logger.warning(f"[{svc}] 🔄 전체 재정렬 감지 → Tail 업데이트 후 재부트스트랩 트리거")
            state["last_total_count"] = new_tail
            state["pivots"] = {}
            state["_bootstrapping"] = True
            self.state_repo.save_state(self.service_id, state)

            def _bg_bootstrap():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.diff_bootstrapper._run_bootstrap_standalone())
                finally:
                    loop.close()
            threading.Thread(target=_bg_bootstrap, daemon=True, name=f"rebootstrap-{svc}").start()
            logger.info(f"[{svc}] 🔄 백그라운드 재부트스트랩 시작됨")
            return []

        new_data_rows = await self._download_new_rows(pivot_indices, shift_amounts, old_tail, new_tail, diff_count)

        new_pivots = await self.pivot_analyzer.update_pivots(pivot_indices, pivots, shift_amounts, new_tail, diff_count)
        state["last_total_count"] = new_tail
        state["pivots"] = new_pivots
        self.state_repo.save_state(self.service_id, state)

        logger.info(f"[{svc}] 💾 신규 변동분 {len(new_data_rows):,}건 수집 완료. (tail {old_tail:,} → {new_tail:,})")
        return new_data_rows
