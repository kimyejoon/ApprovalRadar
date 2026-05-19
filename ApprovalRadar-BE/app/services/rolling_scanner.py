"""
Rolling Full Scan 서비스 모듈 (2-Track 아키텍처).

=== Track 1: Sequential Scan (듀얼 커서 A/B) ===
전체 데이터를 순차적으로 스캔하여 과거 누락 데이터를 보완합니다.
- cursor_a: 전반부 (0 ~ mid) 순차 스캔
- cursor_b: 후반부 (mid ~ end) 순차 스캔

=== Track 2: Random Probe ===
전체 범위에서 랜덤 페이지를 샘플링하여 오늘 변동분을 빠르게 감지합니다.
- 매 주기 30% 페이지를 랜덤 위치에서 스캔
- Sequential이 아직 미도달한 구간의 오늘 데이터를 확률적으로 감지
- Tail Ping 부스트 시 Random 비중 50%로 증가

상태 (crawler_state.extra_state에 영속):
  - rolling_cursor_a: 전반부 스캔 위치
  - rolling_cursor_b: 후반부 스캔 위치
  - page_fingerprints: {page_start_idx: fingerprint_hash}
"""
import asyncio
import random
from datetime import datetime
from app.core.config import settings
from app.core.logger import logger
from app.services.pivot_manager import compute_page_fingerprint

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수


class RollingScanner:
    def __init__(self, api_client, service_id: str, state_repo):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = state_repo

    async def scan_cycle(self, pages_per_cycle: int = None, flush_callback=None, boosted: bool = False) -> list:
        """
        2-Track Rolling Scan: Sequential(A+B) + Random Probe.

        Args:
            pages_per_cycle: 주기당 총 스캔 페이지 수
            flush_callback: async callable(rows) — 각 트랙 완료 시 즉시 호출.
            boosted: True면 Random Probe 비중 증가 (Tail Ping 트리거 시)

        Returns:
            list: 새로 발견된 레코드 리스트 (flush_callback 미사용 시)
        """
        svc = self.service_id
        if pages_per_cycle is None:
            pages_per_cycle = settings.ROLLING_SCAN_PAGES_PER_CYCLE

        state = self.state_repo.load_state(svc)
        total_count = state.get("last_total_count", 0)
        if total_count == 0:
            return []

        # 전체 페이지 수 및 중간점 계산
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        if total_pages == 0:
            return []

        mid_record = ((total_count // 2) // PAGE_SIZE) * PAGE_SIZE + 1  # mid 정렬

        # ── 2-Track 페이지 분배 ──
        # 일반: Sequential 70% + Random 30%
        # 부스트(Tail Ping 트리거): Sequential 50% + Random 50%
        if boosted:
            pages_random = pages_per_cycle // 2
        else:
            pages_random = max(10, pages_per_cycle * 3 // 10)  # 최소 10p
        pages_sequential = pages_per_cycle - pages_random

        # 듀얼 커서 로드
        cursor_a = state.get("rolling_cursor_a", 1)
        cursor_b = state.get("rolling_cursor_b", mid_record)
        fingerprints: dict = state.get("page_fingerprints", {})
        scan_times: dict = state.get("page_scan_times", {})

        # 각 커서에 절반씩 할당
        pages_a = pages_sequential // 2
        pages_b = pages_sequential - pages_a

        # 영역 범위
        range_a = (1, mid_record - 1)           # 전반부
        range_b = (mid_record, total_count)     # 후반부

        pages_a_total = (range_a[1]) // PAGE_SIZE if range_a[1] > 0 else 0
        pages_b_total = ((range_b[1] - range_b[0] + 1) + PAGE_SIZE - 1) // PAGE_SIZE if range_b[1] >= range_b[0] else 0

        mode = "🚀 BOOST" if boosted else "🔄 일반"
        logger.info(
            f"[{svc}] {mode} Rolling Scan 시작 (2-Track): "
            f"Sequential A={cursor_a:,}~{range_a[1]:,} ({pages_a}p) + B={cursor_b:,}~{range_b[1]:,} ({pages_b}p) | "
            f"Random Probe {pages_random}p | "
            f"전체={total_pages}p ({total_count:,}건)"
        )

        new_rows_total = []
        mismatched_pages = 0
        total_scanned = 0

        # ── 커서 A 스캔 (전반부) ──
        scanned_a, new_a, mismatch_a, cursor_a = await self._scan_range(
            svc, cursor_a, range_a[0], range_a[1],
            pages_a, fingerprints, scan_times, "A"
        )
        mismatched_pages += mismatch_a
        total_scanned += scanned_a
        # 커서 A 완료 즉시 flush → DB INSERT + SSE 발행
        if new_a and flush_callback:
            await flush_callback(new_a)
            logger.info(
                f"[{svc}] ⚡ 커서 A 즉시 flush: {len(new_a)}건 → scraper 파이프라인"
            )
        elif new_a:
            new_rows_total.extend(new_a)

        # ── 커서 B 스캔 (후반부) ──
        scanned_b, new_b, mismatch_b, cursor_b = await self._scan_range(
            svc, cursor_b, range_b[0], range_b[1],
            pages_b, fingerprints, scan_times, "B"
        )
        mismatched_pages += mismatch_b
        total_scanned += scanned_b
        # 커서 B 완료 즉시 flush
        if new_b and flush_callback:
            await flush_callback(new_b)
            logger.info(
                f"[{svc}] ⚡ 커서 B 즉시 flush: {len(new_b)}건 → scraper 파이프라인"
            )
        elif new_b:
            new_rows_total.extend(new_b)

        # ── Track 2: Random Probe ──
        scanned_r, new_r = await self._scan_random_probe(
            svc, pages_random, total_count, cursor_a, cursor_b, range_a, range_b, scan_times
        )
        total_scanned += scanned_r
        if new_r and flush_callback:
            await flush_callback(new_r)
            logger.info(
                f"[{svc}] ⚡ Random Probe 즉시 flush: {len(new_r)}건 → scraper 파이프라인"
            )
        elif new_r:
            new_rows_total.extend(new_r)

        # 상태 영속화
        state["rolling_cursor_a"] = cursor_a
        state["rolling_cursor_b"] = cursor_b
        state["page_fingerprints"] = fingerprints
        state["page_scan_times"] = scan_times
        # 구버전 호환: 단일 커서 키 제거
        state.pop("rolling_cursor", None)
        self.state_repo.save_state(svc, state)

        # 남은 페이지 계산
        remaining_a = max(0, ((range_a[1] - cursor_a + 1) + PAGE_SIZE - 1) // PAGE_SIZE) if cursor_a <= range_a[1] else pages_a_total
        remaining_b = max(0, ((range_b[1] - cursor_b + 1) + PAGE_SIZE - 1) // PAGE_SIZE) if cursor_b <= range_b[1] else pages_b_total
        max_remaining = max(remaining_a, remaining_b)
        half_pages = max(pages_a, pages_b)
        cycles_to_complete = (max_remaining + half_pages - 1) // half_pages if half_pages > 0 else 0

        flushed_total = (len(new_a) if new_a and flush_callback else 0) + \
                        (len(new_b) if new_b and flush_callback else 0) + \
                        (len(new_r) if new_r and flush_callback else 0)

        logger.info(
            f"[{svc}] ✅ Rolling Scan 완료: "
            f"{total_scanned}p (Seq A:{scanned_a}+B:{scanned_b} | Rand:{scanned_r}), "
            f"{mismatched_pages}건 불일치, "
            f"{flushed_total + len(new_rows_total)}건 수집 | "
            f"다음 A={cursor_a:,}, B={cursor_b:,} | "
            f"약 {cycles_to_complete}주기 후 1회전 완료"
        )

        return new_rows_total

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
        db_miss_count = 0  # DB 미존재 레코드 수
        today_str = datetime.now().strftime("%Y%m%d")

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

                        # 오늘 변동분 카운팅
                        today_in_missing = sum(
                            1 for item in missing_items
                            if item.get("CHNG_DT", "") == today_str
                        )
                        if today_in_missing:
                            today_found += today_in_missing
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
                scan_times[str(page_start)] = datetime.now().strftime("%H:%M:%S")

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
                        f"DB미존재:{db_miss_count} 오늘:{today_found}){insight}"
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
        logger.info(
            f"[{svc}] ✅ 커서 {label} 완료: {scanned}p 스캔 "
            f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
            f"DB미존재:{db_miss_count} 오늘:{today_found}) → {len(new_rows)}건 수집"
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
                    scan_times[str(page_start)] = datetime.now().strftime("%H:%M:%S")

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

                # 오늘 CHNG_DT 체크
                page_today = sum(1 for item in items if item.get("CHNG_DT", "").startswith(today_str))
                if page_today > 0:
                    today_found += page_today
                    logger.info(
                        f"[{svc}] 🎯 오늘 데이터 발견! page {page_start:,}: "
                        f"{page_today}건 (CHNG_DT={today_str})"
                    )

                # 10p마다 진행 로그
                if scanned % 10 == 0:
                    logger.info(
                        f"[{svc}] 📊 Random Probe 진행: {scanned}/{sample_size}p "
                        f"(DB미존재:{db_miss_count} 오늘:{today_found})"
                    )

                await asyncio.sleep(0.3)

        finally:
            try:
                db_conn.close()
            except Exception:
                pass

        logger.info(
            f"[{svc}] ✅ Random Probe 완료: {scanned}p → "
            f"{len(new_rows)}건 수집 (DB미존재:{db_miss_count} 오늘:{today_found})"
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
