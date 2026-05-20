"""Rolling Full Scan 서비스 모듈.

스캔 모드:
  OLDEST_FIRST — 순수 Oldest-First. 모든 페이지를 연식순 스캔. (기본값)
  HYBRID       — Oldest-First 70% + Random Probe 30%. (레거시)

상태 (crawler_state.extra_state에 영속):
  - page_fingerprints: {page_start_idx: fingerprint_hash}
  - page_scan_times:   {page_start_idx: ISO timestamp}
"""
import asyncio
import random
from enum import Enum
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event
from app.services.pivot_manager import compute_page_fingerprint

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수


class ScanMode(Enum):
    """스캔 전략 모드. config 또는 코드에서 선택."""
    OLDEST_FIRST = "oldest_first"  # 순수 연식순 (추천)
    HYBRID = "hybrid"              # Oldest 70% + Random 30% (레거시)


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
        """
        Rolling Scan 메인 진입점.

        Args:
            pages_per_cycle: 주기당 총 스캔 페이지 수
            flush_callback: async callable(rows) — 발견 즉시 호출
            boosted: True면 Random Probe 비중 증가 (HYBRID 전용)
            mode: ScanMode.OLDEST_FIRST | ScanMode.HYBRID
        """
        if mode == ScanMode.HYBRID:
            return await self._scan_hybrid(pages_per_cycle, flush_callback, boosted)
        return await self._scan_oldest_first(pages_per_cycle, flush_callback)

    # ══════════════════════════════════════════════════════════════
    # Mode: OLDEST_FIRST — 순수 연식순 (100% 유효 스캔)
    # ══════════════════════════════════════════════════════════════

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
        migrated = self._migrate_scan_times(scan_times)
        if migrated > 0:
            logger.info(f"[{svc}] 🔧 scan_times 마이그레이션: {migrated}건 HH:MM:SS → ISO 변환")

        # ── 연식 1h 이상 페이지: pages_per_cycle 제한 없이 전부 포함 ──
        # 1h 이상이면 해당 주기에 반드시 스캔해야 하는 고우선 페이지
        STALE_AGE_SEC = 3600  # 1시간
        stale_pages = self._select_oldest_pages(scan_times, total_pages, total_pages, min_age_sec=STALE_AGE_SEC)
        fresh_budget = max(0, pages_per_cycle - len(stale_pages))
        # 1h 미만 페이지: 남은 예산만큼만 추가 (Oldest-First 순)
        fresh_pages = self._select_oldest_pages(scan_times, total_pages, fresh_budget, min_age_sec=0)
        # stale 중복 제거
        stale_set = set(stale_pages)
        fresh_pages = [p for p in fresh_pages if p not in stale_set]
        oldest_pages = stale_pages + fresh_pages

        if oldest_pages:
            max_age = self._get_page_age(scan_times, oldest_pages[0])
            min_age = self._get_page_age(scan_times, oldest_pages[-1])
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
            scanned, new_rows, mismatch, api_rows = await self._scan_single_page(
                svc, page_start, total_count, fingerprints, scan_times
            )
            total_scanned += scanned
            mismatched_pages += mismatch
            if scanned > 0:
                fp_key = str(page_start)
                # 신규FP vs 일치 분류 (scan 후 fingerprints 이미 갱신됨)
                if mismatch:
                    pass  # mismatched_pages 이미 집계
                else:
                    # 기존 FP 있고 일치 → matched
                    # 신규 FP (첫 스캔) → new_fp
                    if fp_key in fingerprints and fp_key in scan_times:
                        matched_pages += 1
                    else:
                        new_fp_pages += 1

            # 오늘/어제 건수 집계 — API 응답 전체 rows 기준 (fingerprint 일치 여부 무관)
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

            # 매 25p마다 진행률 로그 (상세 통계 포함)
            if total_scanned > 0 and total_scanned % 25 == 0:
                elapsed = (datetime.now() - scan_start).total_seconds()
                pace = elapsed / total_scanned  # 초/페이지
                remaining = (len(oldest_pages) - total_scanned) * pace
                logger.info(
                    f"[{svc}] 📊 스캔 진행: {total_scanned}/{len(oldest_pages)}p "
                    f"({total_scanned/len(oldest_pages)*100:.0f}%) | "
                    f"일치:{matched_pages} 불일치:{mismatched_pages} 신규FP:{new_fp_pages} "
                    f"오늘:{today_found_total}(API) 어제:{yesterday_found_total}(API) "
                    f"수집:{flushed_count + len(new_rows_total)}(write) |"
                    f"경과:{elapsed:.0f}초 잔여:{remaining:.0f}초"
                )

        # 상태 영속화
        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        self.state_repo.save_state(svc, state)

        scanned_page_count = sum(1 for k in scan_times if scan_times[k])
        coverage_pct = round(scanned_page_count / total_pages * 100, 1) if total_pages > 0 else 0
        elapsed_total = (datetime.now() - scan_start).total_seconds()

        all_ages = sorted([self._get_page_age(scan_times, p*PAGE_SIZE+1) for p in range(total_pages)], reverse=True)
        worst_age = all_ages[0] if all_ages else 0

        # 다음 주기 예정 시간 조회
        next_run_str = "미등록"
        try:
            from app.core.scheduler import scheduler
            job = scheduler.get_job("scraper_job")
            if job and job.next_run_time:
                next_run_str = job.next_run_time.strftime("%H:%M:%S")
        except Exception:
            pass

        # API 호출 횟수 조회
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
            f"최대연식: {worst_age:.1f}h | 다음주기: {next_run_str} | API호출: {api_calls}회"
        )
        return new_rows_total

    # ══════════════════════════════════════════════════════════════
    # Mode: HYBRID — Oldest-First + Random Probe (레거시, 회귀용 보존)
    # ══════════════════════════════════════════════════════════════

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
        oldest_pages = self._select_oldest_pages(scan_times, total_pages, pages_oldest, MIN_AGE_SEC)

        if oldest_pages:
            max_age = self._get_page_age(scan_times, oldest_pages[0])
            min_age = self._get_page_age(scan_times, oldest_pages[-1])
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
            scanned, new_rows, mismatch, api_rows = await self._scan_single_page(
                svc, page_start, total_count, fingerprints, scan_times
            )
            total_scanned += scanned
            mismatched_pages += mismatch
            if new_rows and flush_callback:
                await flush_callback(new_rows)
            elif new_rows:
                new_rows_total.extend(new_rows)

        scanned_r, new_r = await self._scan_random_probe(
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

    @staticmethod
    def _parse_scan_time(value: str) -> datetime | None:
        """scan_times 값을 datetime으로 파싱. ISO/HH:MM:SS 모두 지원."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            pass
        # 레거시 HH:MM:SS → 오늘 날짜 + 시간으로 해석
        try:
            t = datetime.strptime(value, "%H:%M:%S").time()
            return datetime.combine(datetime.now().date(), t)
        except (ValueError, TypeError):
            return None

    def _migrate_scan_times(self, scan_times: dict) -> int:
        """HH:MM:SS 레거시 값을 ISO datetime으로 일괄 변환."""
        migrated = 0
        today = datetime.now().date()
        for k, v in list(scan_times.items()):
            if v and 'T' not in str(v):
                try:
                    t = datetime.strptime(v, "%H:%M:%S").time()
                    scan_times[k] = datetime.combine(today, t).isoformat()
                    migrated += 1
                except (ValueError, TypeError):
                    del scan_times[k]
                    migrated += 1
        return migrated

    def _select_oldest_pages(self, scan_times: dict, total_pages: int, count: int, min_age_sec: int = 3600) -> list:
        """
        경과 시간 기준으로 가장 오래된 페이지 count개 선택.
        미스캔 페이지(scan_times에 없는)가 최우선.
        """
        now = datetime.now()
        candidates = []
        for page_idx in range(total_pages):
            page_start = page_idx * PAGE_SIZE + 1
            key = str(page_start)
            last_scan = scan_times.get(key)
            if last_scan is None:
                age = float('inf')
            else:
                parsed = self._parse_scan_time(last_scan)
                age = (now - parsed).total_seconds() if parsed else float('inf')
            if age >= min_age_sec:
                candidates.append((page_start, age))

        candidates.sort(key=lambda x: -x[1])
        return [c[0] for c in candidates[:count]]

    def _get_page_age(self, scan_times: dict, page_start: int) -> float:
        """페이지의 연식(시간)을 반환."""
        key = str(page_start)
        last_scan = scan_times.get(key)
        if last_scan is None:
            return 999.9
        parsed = self._parse_scan_time(last_scan)
        if parsed is None:
            return 999.9
        return (datetime.now() - parsed).total_seconds() / 3600

    async def _scan_single_page(
        self, svc: str, page_start: int, total_count: int,
        fingerprints: dict, scan_times: dict
    ) -> tuple:
        """
        단일 페이지 스캔 + fingerprint 비교.
        Returns: (scanned_count, new_rows, mismatch_count)
        """
        from app.core.events import shutdown_event
        if shutdown_event.is_set():
            return (0, [], 0)

        page_end = min(page_start + PAGE_SIZE - 1, total_count)
        fp_key = str(page_start)

        try:
            data = await self.api_client.fetch_data(
                self.service_id, page_start, page_end
            )
        except Exception as e:
            logger.warning(f"[{svc}] ⚠ 페이지 {page_start:,} API 실패 → skip 후 계속: {e}")
            return (0, [], 0, [])  # 실패해도 크래시 없이 다음 페이지로

        if not data or self.service_id not in data:
            return (1, [], 0, [])  # 빈 응답도 scan 카운트는 +1 (시도는 했음)

        rows = data[self.service_id].get("row", [])
        if not rows:
            return (1, [], 0, [])

        # Fingerprint 비교
        new_fp = compute_page_fingerprint(rows)
        old_fp = fingerprints.get(fp_key)
        fingerprints[fp_key] = new_fp
        scan_times[fp_key] = datetime.now().isoformat()

        mismatch = 0
        new_rows = []

        if old_fp and old_fp != new_fp:
            mismatch = 1
            # 불일치 → DB에 없는 레코드 찾기
            from database import get_db
            today_str = datetime.now().strftime("%Y%m%d")
            yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

            lcns_list = [r.get("LCNS_NO", "") for r in rows if r.get("LCNS_NO")]
            existing_set = set()
            if lcns_list:
                with get_db() as conn:
                    ph = ",".join(["?"] * len(lcns_list))
                    db_rows = conn.execute(
                        f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({ph})",
                        lcns_list
                    ).fetchall()
                    for r in db_rows:
                        existing_set.add((r["license_no"], r["last_event_date"]))

            for row in rows:
                lcns = row.get("LCNS_NO", "")
                chng_dt = row.get("CHNG_DT", "")
                if lcns and chng_dt in (today_str, yesterday_str):
                    if (lcns, chng_dt) not in existing_set:
                        new_rows.append(row)

        return (1, new_rows, mismatch, rows)  # rows = API 응답 전체 (CHNG_DT 집계용)

    async def _scan_range(
        self, svc: str, cursor: int,
        range_start: int, range_end: int,
        max_pages: int, fingerprints: dict, scan_times: dict,
        label: str
    ) -> tuple:
        """
        지정된 범위 내에서 cursor부터 max_pages만큼 스캔합니다.
        [최적화] DB에 없는 레코드를 batch로 감지하여 즉시 수집.

        Returns:
            (scanned_count, new_rows, mismatch_count, new_cursor)
        """
        scanned = 0
        new_rows = []
        mismatched = 0
        new_fp_count = 0  # 신규 fingerprint 저장 수
        match_count = 0   # fingerprint 일치 수
        today_found = 0   # 오늘 CHNG_DT 신규 발견 수
        yesterday_found = 0  # 어제 CHNG_DT 신규 발견 수
        db_miss_count = 0  # DB 미존재 레코드 수
        today_str = datetime.now().strftime("%Y%m%d")
        from datetime import timedelta
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        # ── 인사이트 통계 수집용 ──
        all_chng_dts = []   # 전체 CHNG_DT 수집 (분포 분석)
        lcns_sort_asc = 0   # LCNS_NO 오름차순 페이지 수
        lcns_sort_desc = 0  # LCNS_NO 내림차순 페이지 수
        lcns_no_sort = 0    # 정렬 불명 페이지 수

        # DB batch 조회용 — 스레드 로컬 캐싱 커넥션 (close하지 않음)
        # DB batch 조회용 — 스캔 전체에서 재사용할 커넥션
        import sqlite3
        from database import DB_FILE
        db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        db_conn.row_factory = sqlite3.Row

        logger.info(
            f"[{svc}] 📡 커서 {label} 스캔 시작: "
            f"범위 {cursor:,}~{range_end:,}, 최대 {max_pages}페이지 (오늘={today_str})"
        )

        try:
            while scanned < max_pages:
                page_start = cursor

                if page_start > range_end:
                    # 영역 끝 도달 → 영역 시작으로 리셋
                    cursor = range_start
                    logger.info(
                        f"[{svc}] 🔁 커서 {label} 1회전 완료! "
                        f"cursor를 {range_start:,}으로 리셋"
                    )
                    break

                # API 호출
                page_end = min(page_start + PAGE_SIZE - 1, range_end)
                try:
                    res = await self.api_client.fetch_data(
                        svc, page_start, page_end, timeout=30
                    )
                    await asyncio.sleep(
                        random.uniform(settings.GAP_MIN, settings.GAP_MAX)
                    )

                    if not res or svc not in res:
                        cursor += PAGE_SIZE
                        scanned += 1
                        continue

                    block = res[svc]
                    code = block.get("RESULT", {}).get("CODE", "")

                    if code in ("INFO-200", "") or code != "INFO-000":
                        cursor += PAGE_SIZE
                        scanned += 1
                        continue

                    items = block.get("row", [])
                    if not items:
                        cursor += PAGE_SIZE
                        scanned += 1
                        continue

                except Exception as e:
                    logger.warning(
                        f"[{svc}] Rolling Scan {label} page {page_start:,} 조회 실패: {e}"
                    )
                    cursor += PAGE_SIZE
                    scanned += 1
                    continue

                # ── DB 미존재 이벤트 batch 감지 ──────────────────
                # (LCNS_NO, CHNG_DT) 쌍으로 확인 — 동일 LCNS라도
                # 다른 CHNG_DT면 별도 인허가변동 이력이므로 수집 대상
                lcns_list = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]
                if lcns_list:
                    # batch 조회: DB에 이미 있는 (license_no, last_event_date) 쌍
                    placeholders = ",".join(["?"] * len(lcns_list))
                    existing_cursor = db_conn.execute(
                        f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({placeholders})",
                        lcns_list
                    )
                    existing_pairs = {(row[0], row[1]) for row in existing_cursor.fetchall()}

                    # DB에 (LCNS, CHNG_DT) 쌍이 없는 레코드 = 신규 이력 → 수집
                    missing_items = [
                        item for item in items
                        if item.get("LCNS_NO", "")
                        and (item["LCNS_NO"], item.get("CHNG_DT", "")) not in existing_pairs
                    ]
                    if missing_items:
                        db_miss_count += len(missing_items)
                        new_rows.extend(missing_items)

                        today_in_missing = sum(
                            1 for item in missing_items
                            if item.get("CHNG_DT", "") == today_str
                        )
                        yesterday_in_missing = sum(
                            1 for item in missing_items
                            if item.get("CHNG_DT", "") == yesterday_str
                        )
                        if today_in_missing:
                            today_found += today_in_missing
                        if yesterday_in_missing:
                            yesterday_found += yesterday_in_missing
                            logger.info(
                                f"[{svc}] 🆕 커서 {label} page {page_start:,}: "
                                f"오늘({today_str}) 변동분 {today_in_missing}건 즉시 감지!"
                            )

                        if len(missing_items) >= 5:
                            logger.info(
                                f"[{svc}] 📥 커서 {label} page {page_start:,}: "
                                f"DB 미존재 {len(missing_items)}건 발견 → 수집 대상 추가"
                            )

                # ── fingerprint 비교 ──────────────────────────────────
                current_fp = compute_page_fingerprint(items)
                stored_fp = fingerprints.get(str(page_start), "")

                # 스캔 시각 기록
                scan_times[str(page_start)] = datetime.now().isoformat()

                if not stored_fp:
                    # 첫 스캔: fingerprint 신규 저장
                    new_fp_count += 1
                elif current_fp == stored_fp:
                    # 일치: 변동 없음
                    match_count += 1
                else:
                    # 불일치: 변동 감지!
                    mismatched += 1
                    # DB miss 체크에서 이미 수집했으므로 중복 추가 방지
                    logger.debug(
                        f"[{svc}] 커서 {label} page {page_start:,}: "
                        f"fingerprint 불일치 (DB miss 체크에서 이미 처리)"
                    )

                # ── [인사이트] 페이지별 CHNG_DT/LCNS_NO 통계 ──────────────
                page_chng_dts = [item.get("CHNG_DT", "") for item in items if item.get("CHNG_DT")]
                all_chng_dts.extend(page_chng_dts)

                # LCNS_NO 정렬 패턴 분석
                lcns_nos = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]
                if len(lcns_nos) >= 2:
                    is_asc = all(lcns_nos[i] <= lcns_nos[i+1] for i in range(min(10, len(lcns_nos)-1)))
                    is_desc = all(lcns_nos[i] >= lcns_nos[i+1] for i in range(min(10, len(lcns_nos)-1)))
                    if is_asc:
                        lcns_sort_asc += 1
                    elif is_desc:
                        lcns_sort_desc += 1
                    else:
                        lcns_no_sort += 1

                # fingerprint 갱신
                fingerprints[str(page_start)] = current_fp
                cursor += PAGE_SIZE
                scanned += 1

                # 매 10페이지마다 진행률 + 인사이트 로그
                if scanned % 10 == 0:
                    # CHNG_DT 분포 분석
                    insight = ""
                    if all_chng_dts:
                        sorted_dts = sorted(all_chng_dts)
                        oldest = sorted_dts[0]
                        newest = sorted_dts[-1]
                        # 연도별 분포 요약
                        year_dist = {}
                        for dt in all_chng_dts:
                            yr = dt[:4] if len(dt) >= 4 else "????"
                            year_dist[yr] = year_dist.get(yr, 0) + 1
                        top_years = sorted(year_dist.items(), key=lambda x: -x[1])[:3]
                        yr_summary = " ".join(f"{y}:{c}" for y, c in top_years)
                        sort_pattern = (
                            f"LCNS정렬:↑{lcns_sort_asc}/↓{lcns_sort_desc}/∅{lcns_no_sort}"
                        )
                        insight = f" | DT범위:{oldest}~{newest} 연도분포:[{yr_summary}] {sort_pattern}"

                    logger.info(
                        f"[{svc}] 📊 커서 {label} 진행: {scanned}/{max_pages}p "
                        f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
                        f"DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found}){insight}"
                    )

        finally:
            try:
                db_conn.close()
            except Exception:
                pass

        # 커서별 완료 요약
        if today_found > 0:
            logger.info(
                f"[{svc}] 🆕 커서 {label}: 오늘({today_str}) 변동분 {today_found}건 즉시 감지!"
            )
        if yesterday_found > 0:
            logger.info(
                f"[{svc}] 📋 커서 {label}: 어제({yesterday_str}) 변동분 {yesterday_found}건 감지"
            )
        logger.info(
            f"[{svc}] ✅ 커서 {label} 완료: {scanned}p 스캔 "
            f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
            f"DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found}) → {len(new_rows)}건 수집"
        )

        return scanned, new_rows, mismatched, cursor

    async def _scan_random_probe(
        self, svc: str, max_pages: int, total_count: int,
        cursor_a: int, cursor_b: int,
        range_a: tuple, range_b: tuple,
        scan_times: dict | None = None
    ) -> tuple:
        """
        Track 2: 전체 범위에서 랜덤 페이지를 샘플링하여 DB 미존재 레코드를 수집합니다.
        Sequential 커서가 현재 스캔 중인 근방은 제외하여 중복을 방지합니다.

        Returns:
            (scanned_count, new_rows)
        """
        today_str = datetime.now().strftime("%Y%m%d")
        from datetime import timedelta as _td
        yesterday_str = (datetime.now() - _td(days=1)).strftime("%Y%m%d")
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE

        # Sequential 커서 근방 제외 (±30p 범위)
        exclude_margin = 30 * PAGE_SIZE
        exclude_a = set(range(
            max(1, cursor_a - exclude_margin),
            min(total_count, cursor_a + exclude_margin) + 1,
            PAGE_SIZE
        ))
        exclude_b = set(range(
            max(1, cursor_b - exclude_margin),
            min(total_count, cursor_b + exclude_margin) + 1,
            PAGE_SIZE
        ))
        excluded = exclude_a | exclude_b

        # 전체 가능 페이지 시작 위치 생성
        all_page_starts = [
            p * PAGE_SIZE + 1 for p in range(total_pages)
            if (p * PAGE_SIZE + 1) not in excluded
        ]

        if not all_page_starts:
            return 0, []

        # 랜덤 샘플링
        sample_size = min(max_pages, len(all_page_starts))
        sampled_starts = sorted(random.sample(all_page_starts, sample_size))

        logger.info(
            f"[{svc}] 🎲 Random Probe 시작: {sample_size}p "
            f"(전체 {len(all_page_starts)}p 중 랜덤 샘플링, 오늘={today_str})"
        )

        scanned = 0
        new_rows = []
        today_found = 0
        yesterday_found = 0
        db_miss_count = 0

        # DB batch 조회용 커넥션
        import sqlite3
        from database import DB_FILE
        db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        db_conn.row_factory = sqlite3.Row

        try:
            for page_start in sampled_starts:
                page_end = min(page_start + PAGE_SIZE - 1, total_count)

                try:
                    res = await self.api_client.fetch_data(
                        svc, page_start, page_end, timeout=15
                    )
                except Exception:
                    continue

                if not res or svc not in res:
                    continue

                block = res[svc]
                code = block.get("RESULT", {}).get("CODE", "")
                if code != "INFO-000":
                    continue

                items = block.get("row", [])
                if not items:
                    continue

                scanned += 1

                # 스캔 시각 기록
                if scan_times is not None:
                    scan_times[str(page_start)] = datetime.now().isoformat()

                # DB batch miss 체크
                lcns_list = []
                for item in items:
                    ln = item.get("LCNS_NO", "")
                    if ln:
                        lcns_list.append(ln)

                if lcns_list:
                    unique_lcns = list(set(lcns_list))
                    placeholders = ",".join(["?"] * len(unique_lcns))
                    existing = set()
                    cursor = db_conn.execute(
                        f"SELECT license_no FROM businesses WHERE license_no IN ({placeholders})",
                        unique_lcns
                    )
                    for row in cursor.fetchall():
                        existing.add(row["license_no"])

                    page_new = [item for item in items if item.get("LCNS_NO", "") and item.get("LCNS_NO") not in existing]
                    if page_new:
                        db_miss_count += len(page_new)
                        new_rows.extend(page_new)

                # 오늘/어제 CHNG_DT 체크
                page_today = sum(1 for item in items if item.get("CHNG_DT", "").startswith(today_str))
                page_yesterday = sum(1 for item in items if item.get("CHNG_DT", "").startswith(yesterday_str))
                if page_today > 0:
                    today_found += page_today
                    logger.info(
                        f"[{svc}] 🎯 오늘 데이터 발견! page {page_start:,}: "
                        f"{page_today}건 (CHNG_DT={today_str})"
                    )
                if page_yesterday > 0:
                    yesterday_found += page_yesterday

                # 10p마다 진행 로그
                if scanned % 10 == 0:
                    logger.info(
                        f"[{svc}] 📊 Random Probe 진행: {scanned}/{sample_size}p "
                        f"(DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found})"
                    )

                await asyncio.sleep(0.3)

        finally:
            try:
                db_conn.close()
            except Exception:
                pass

        logger.info(
            f"[{svc}] ✅ Random Probe 완료: {scanned}p → "
            f"{len(new_rows)}건 수집 (DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found})"
        )

        return scanned, new_rows

    def _extract_new_rows(
        self, current_items: list, fingerprints: dict, page_start: int
    ) -> list:
        """
        fingerprint 불일치 페이지에서 신규 삽입 레코드를 추출합니다.
        """
        return current_items

    @staticmethod
    def build_fingerprints_from_bootstrap(
        api_client, service_id: str, total_count: int
    ) -> dict:
        """Bootstrap 호환용 — 실제 fingerprint는 scan_cycle 중 점진적으로 채워짐."""
        return {}
