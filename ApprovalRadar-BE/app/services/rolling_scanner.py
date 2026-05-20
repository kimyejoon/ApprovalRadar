"""Rolling Full Scan 서비스 모듈.

스캔 모드:
  OLDEST_FIRST — 순수 Oldest-First. 모든 페이지를 연식순 스캔. (기본값)
  HYBRID       — Oldest-First 70% + Random Probe 30%. (레거시)

상태 (crawler_state.extra_state에 영속):
  - page_fingerprints: {page_start_idx: fingerprint_hash}
  - page_scan_times:   {page_start_idx: ISO timestamp}
"""
from enum import Enum
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event

from app.services.crawler_constants import PAGE_SIZE
from app.services.rolling_scan_utils import migrate_scan_times, select_oldest_pages, get_page_age
from app.services.rolling_scan_ops import RollingScanOps


class ScanMode(Enum):
    """스캔 전략 모드. config 또는 코드에서 선택."""
    OLDEST_FIRST = "oldest_first"  # 순수 연식순 (추천)
    HYBRID = "hybrid"              # Oldest 70% + Random 30% (레거시)


class RollingScanner:
    def __init__(self, api_client, service_id: str, state_repo):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = state_repo
        self.ops = RollingScanOps(api_client, service_id)

    async def scan_cycle(
        self,
        pages_per_cycle: int = None,
        flush_callback=None,
        boosted: bool = False,
        mode: ScanMode = ScanMode.OLDEST_FIRST,
    ) -> list:
        """
        Rolling Scan 메인 진입점.
        """
        if mode == ScanMode.HYBRID:
            return await self._scan_hybrid(pages_per_cycle, flush_callback, boosted)
        return await self._scan_oldest_first(pages_per_cycle, flush_callback)

    async def _scan_oldest_first(self, pages_per_cycle: int = None, flush_callback=None) -> list:
        svc = self.service_id
        if pages_per_cycle is None:
            pages_per_cycle = settings.ROLLING_SCAN_PAGES_PER_CYCLE

        state = self.state_repo.load_state(svc)
        total_count = state.get("last_total_count", 0)
        if total_count == 0:
            return []

        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        if total_pages == 0:
            return []

        fingerprints: dict = state.get("page_fingerprints", {})
        scan_times: dict = state.get("page_scan_times", {})

        # 레거시 HH:MM:SS → ISO 자동 마이그레이션
        migrated = migrate_scan_times(scan_times)
        if migrated > 0:
            logger.info(f"[{svc}] 🔧 scan_times 마이그레이션: {migrated}건 HH:MM:SS → ISO 변환")

        STALE_AGE_SEC = 3600  # 1시간
        stale_pages = select_oldest_pages(scan_times, total_pages, total_pages, PAGE_SIZE, min_age_sec=STALE_AGE_SEC)
        fresh_budget = max(0, pages_per_cycle - len(stale_pages))
        fresh_pages = select_oldest_pages(scan_times, total_pages, fresh_budget, PAGE_SIZE, min_age_sec=0)
        
        stale_set = set(stale_pages)
        fresh_pages = [p for p in fresh_pages if p not in stale_set]
        oldest_pages = stale_pages + fresh_pages

        if oldest_pages:
            max_age = get_page_age(scan_times, oldest_pages[0])
            min_age = get_page_age(scan_times, oldest_pages[-1])
            unscanned = sum(1 for ps in oldest_pages if str(ps) not in scan_times)
        else:
            max_age = min_age = 0.0
            unscanned = 0

        logger.info(
            f"[{svc}] 🔄 Oldest-First Scan: "
            f"{len(oldest_pages)}p (1h↑:{len(stale_pages)}p 포함, 미스캔 {unscanned}p, "
            f"최고연식 {max_age:.1f}h, 최저 {min_age:.1f}h) | "
            f"전체={total_pages}p ({total_count:,}건)"
        )

        new_rows_total = []
        total_scanned = 0
        mismatched_pages = 0
        matched_pages = 0
        new_fp_pages = 0
        flushed_count = 0
        today_found_total = 0
        yesterday_found_total = 0
        scan_start = datetime.now()
        today_str = datetime.now().strftime("%Y%m%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        for page_start in oldest_pages:
            if shutdown_event.is_set():
                break
            scanned, new_rows, mismatch = await self.ops.scan_single_page(
                svc, page_start, total_count, fingerprints, scan_times
            )
            total_scanned += scanned
            mismatched_pages += mismatch
            if scanned > 0:
                fp_key = str(page_start)
                if not mismatch:
                    if fp_key in fingerprints and fp_key in scan_times:
                        matched_pages += 1
                    else:
                        new_fp_pages += 1

            for row in new_rows:
                chng = row.get("CHNG_DT", "")
                if chng == today_str:
                    today_found_total += 1
                elif chng == yesterday_str:
                    yesterday_found_total += 1

            if new_rows and flush_callback:
                await flush_callback(new_rows)
                flushed_count += len(new_rows)
            elif new_rows:
                new_rows_total.extend(new_rows)

            if total_scanned > 0 and total_scanned % 25 == 0:
                elapsed = (datetime.now() - scan_start).total_seconds()
                pace = elapsed / total_scanned
                remaining = (len(oldest_pages) - total_scanned) * pace
                logger.info(
                    f"[{svc}] 📊 스캔 진행: {total_scanned}/{len(oldest_pages)}p "
                    f"({total_scanned/len(oldest_pages)*100:.0f}%) | "
                    f"일치:{matched_pages} 불일치:{mismatched_pages} 신규FP:{new_fp_pages} "
                    f"오늘:{today_found_total} 어제:{yesterday_found_total} "
                    f"수집:{flushed_count + len(new_rows_total)} | "
                    f"경과:{elapsed:.0f}초 잔여:{remaining:.0f}초"
                )

        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        self.state_repo.save_state(svc, state)

        scanned_page_count = sum(1 for k in scan_times if scan_times[k])
        coverage_pct = round(scanned_page_count / total_pages * 100, 1) if total_pages > 0 else 0
        elapsed_total = (datetime.now() - scan_start).total_seconds()

        all_ages = sorted([get_page_age(scan_times, p*PAGE_SIZE+1) for p in range(total_pages)], reverse=True)
        worst_age = all_ages[0] if all_ages else 0

        next_run_str = "미등록"
        try:
            from app.core.scheduler import scheduler
            job = scheduler.get_job("scraper_job")
            if job and job.next_run_time:
                next_run_str = job.next_run_time.strftime("%H:%M:%S")
        except Exception:
            pass

        api_calls = 0
        try:
            api_calls = self.api_client._call_count
        except Exception:
            pass

        total_collected = flushed_count + len(new_rows_total)
        logger.info(
            f"[{svc}] ✅ Oldest-First 완료: {total_scanned}p "
            f"({elapsed_total:.0f}초 소요) | "
            f"일치:{matched_pages} 불일치:{mismatched_pages} 신규FP:{new_fp_pages} "
            f"오늘:{today_found_total} 어제:{yesterday_found_total} 수집:{total_collected}건 | "
            f"커버리지: {scanned_page_count}/{total_pages}p ({coverage_pct}%) | "
            f"최대연식: {worst_age:.1f}h | 다음주기: {next_run_str} | API호출: {api_calls}회"
        )
        return new_rows_total

    async def _scan_hybrid(self, pages_per_cycle: int = None, flush_callback=None, boosted: bool = False) -> list:
        svc = self.service_id
        if pages_per_cycle is None:
            pages_per_cycle = settings.ROLLING_SCAN_PAGES_PER_CYCLE

        state = self.state_repo.load_state(svc)
        total_count = state.get("last_total_count", 0)
        if total_count == 0:
            return []

        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        if total_pages == 0:
            return []

        fingerprints: dict = state.get("page_fingerprints", {})
        scan_times: dict = state.get("page_scan_times", {})

        pages_random = pages_per_cycle // 2 if boosted else max(10, pages_per_cycle * 3 // 10)
        pages_oldest = pages_per_cycle - pages_random

        MIN_AGE_SEC = 3600
        oldest_pages = select_oldest_pages(scan_times, total_pages, pages_oldest, PAGE_SIZE, MIN_AGE_SEC)

        if oldest_pages:
            max_age = get_page_age(scan_times, oldest_pages[0])
            min_age = get_page_age(scan_times, oldest_pages[-1])
            unscanned = sum(1 for ps in oldest_pages if str(ps) not in scan_times)
        else:
            max_age = min_age = 0.0
            unscanned = 0

        mode_label = "🚀 BOOST" if boosted else "🔄 Hybrid"
        logger.info(
            f"[{svc}] {mode_label} Scan: Oldest {len(oldest_pages)}p "
            f"(미스캔 {unscanned}p, 최고연식 {max_age:.1f}h, 최저 {min_age:.1f}h) + "
            f"Random {pages_random}p | 전체={total_pages}p"
        )

        new_rows_total = []
        total_scanned = 0
        mismatched_pages = 0

        for page_start in oldest_pages:
            if shutdown_event.is_set():
                break
            scanned, new_rows, mismatch = await self.ops.scan_single_page(
                svc, page_start, total_count, fingerprints, scan_times
            )
            total_scanned += scanned
            mismatched_pages += mismatch
            if new_rows and flush_callback:
                await flush_callback(new_rows)
            elif new_rows:
                new_rows_total.extend(new_rows)

        scanned_r, new_r = await self.ops.scan_random_probe(
            svc, pages_random, total_count, 1, total_count, (1, total_count), (1, total_count), scan_times
        )
        total_scanned += scanned_r
        if new_r and flush_callback:
            await flush_callback(new_r)
        elif new_r:
            new_rows_total.extend(new_r)

        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        self.state_repo.save_state(svc, state)

        scanned_page_count = sum(1 for k in scan_times if scan_times[k])
        coverage_pct = round(scanned_page_count / total_pages * 100, 1) if total_pages > 0 else 0

        logger.info(
            f"[{svc}] ✅ Hybrid 완료: {total_scanned}p (Oldest:{len(oldest_pages)} + Rand:{scanned_r}), "
            f"{mismatched_pages}건 불일치, {len(new_rows_total)}건 수집 | "
            f"커버리지: {scanned_page_count}/{total_pages}p ({coverage_pct}%)"
        )
        return new_rows_total

    async def _scan_range(self, *args, **kwargs):
        """Delegates to ops for backwards compatibility if needed elsewhere."""
        return await self.ops.scan_range(*args, **kwargs)
