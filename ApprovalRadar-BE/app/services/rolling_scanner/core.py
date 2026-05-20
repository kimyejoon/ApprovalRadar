import asyncio
from enum import Enum
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event

from app.services.rolling_scanner import utils
from app.services.rolling_scanner import tail_tracker

PAGE_SIZE = 1000


class ScanMode(Enum):
    OLDEST_FIRST = "oldest_first"
    HYBRID = "hybrid"


class RollingScanner:
    def __init__(self, api_client, service_id: str, state_repo):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = state_repo

    async def scan_cycle(
        self,
        pages_per_cycle: int = None,
        flush_callback=None,
        boosted: bool = False,
        mode: ScanMode = ScanMode.OLDEST_FIRST,
    ) -> list:
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

        migrated = utils.migrate_scan_times(scan_times)
        if migrated > 0:
            logger.info(f"[{svc}] 🔧 scan_times 마이그레이션: {migrated}건 HH:MM:SS → ISO 변환")

        STALE_AGE_SEC = 3600
        stale_pages = utils.select_oldest_pages(scan_times, total_pages, total_pages, min_age_sec=STALE_AGE_SEC)
        fresh_budget = max(0, pages_per_cycle - len(stale_pages))
        fresh_pages = utils.select_oldest_pages(scan_times, total_pages, fresh_budget, min_age_sec=0)
        
        stale_set = set(stale_pages)
        fresh_pages = [p for p in fresh_pages if p not in stale_set]
        oldest_pages = stale_pages + fresh_pages

        if oldest_pages:
            max_age = utils.get_page_age(scan_times, oldest_pages[0])
            min_age = utils.get_page_age(scan_times, oldest_pages[-1])
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
            scanned, new_rows, mismatch, api_rows = await tail_tracker.scan_single_page(
                self, svc, page_start, total_count, fingerprints, scan_times
            )
            total_scanned += scanned
            mismatched_pages += mismatch
            if scanned > 0:
                fp_key = str(page_start)
                if mismatch:
                    pass
                else:
                    if fp_key in fingerprints and fp_key in scan_times:
                        matched_pages += 1
                    else:
                        new_fp_pages += 1

            for row in api_rows:
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
                    f"오늘:{today_found_total}(API) 어제:{yesterday_found_total}(API) "
                    f"수집:{flushed_count + len(new_rows_total)}(write) |"
                    f"경과:{elapsed:.0f}초 잔여:{remaining:.0f}초"
                )

        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        self.state_repo.save_state(svc, state)

        scanned_page_count = sum(1 for k in scan_times if scan_times[k])
        coverage_pct = round(scanned_page_count / total_pages * 100, 1) if total_pages > 0 else 0
        elapsed_total = (datetime.now() - scan_start).total_seconds()

        all_ages = sorted([utils.get_page_age(scan_times, p*PAGE_SIZE+1) for p in range(total_pages)], reverse=True)
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
            f"오늘:{today_found_total}(API) 어제:{yesterday_found_total}(API) 수집:{total_collected}(write) | "
            f"커버리지: {scanned_page_count}/{total_pages}p ({coverage_pct}%) | "
            f"최대연식: {worst_age:.1f}h | Next: {next_run_str} | API: {api_calls}회"
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
        oldest_pages = utils.select_oldest_pages(scan_times, total_pages, pages_oldest, MIN_AGE_SEC)

        if oldest_pages:
            max_age = utils.get_page_age(scan_times, oldest_pages[0])
            min_age = utils.get_page_age(scan_times, oldest_pages[-1])
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
            scanned, new_rows, mismatch, api_rows = await tail_tracker.scan_single_page(
                self, svc, page_start, total_count, fingerprints, scan_times
            )
            total_scanned += scanned
            mismatched_pages += mismatch
            if new_rows and flush_callback:
                await flush_callback(new_rows)
            elif new_rows:
                new_rows_total.extend(new_rows)

        scanned_r, new_r = await tail_tracker.scan_random_probe(
            self, svc, pages_random, total_count, 1, total_count, (1, total_count), (1, total_count), scan_times
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
