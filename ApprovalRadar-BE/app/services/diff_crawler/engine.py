import asyncio
import random
import time
import json
import datetime
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.repositories.page_scan_repository import PageScanRepository
from app.core.logger import logger

PAGE_SIZE = 1000
STALE_THRESHOLD_SEC = 3600   # 1시간
# 알려진 마지막 페이지 이후 추가 조회할 Tail Probe 페이지 수 (신규 데이터 유입 감지)
TAIL_PROBE_EXTRA = 3
# 업종 경계 프로브: target_boundary 이후 최대 몇 페이지까지 순차 확인할지
INDUSTRY_BOUNDARY_PROBE_MAX = 5

# 모니터링 대상 업종 (수집 필요)
TARGET_INDUSTRIES = {"일반음식점", "휴게음식점", "제과점영업"}
# 수집 불필요 업종 (known_skip 페이지로 분류되면 스캔 제외)
SKIP_INDUSTRIES = {"위탁급식영업", "집단급식소", "유흥주점영업", "단란주점"}


class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()
        self.page_scan_repo = PageScanRepository()

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

    async def _probe_industry_boundary(
        self,
        target_boundary: int,
        total_pages: int,
        page_industries: dict,
        page_labels: dict,
        svc: str,
    ) -> int:
        """
        업종 경계 프로브: target_boundary 바로 다음 페이지부터 한 장씩 순차 확인.
        - TARGET_INDUSTRIES → target_boundary 오른쪽으로 확장, 다음 페이지 계속 확인.
        - SKIP_INDUSTRIES → 정확한 경계 확정, 즉시 STOP.
        - 최대 INDUSTRY_BOUNDARY_PROBE_MAX 페이지까지만 탐색한다.
        반환값: 갱신된 target_boundary
        """
        new_boundary = target_boundary
        for i in range(1, INDUSTRY_BOUNDARY_PROBE_MAX + 1):
            probe_page = target_boundary + i
            if probe_page > total_pages:
                break

            # 이미 업종이 확인된 페이지는 API 호출 없이 판별
            known_ind = page_industries.get(str(probe_page))
            if known_ind:
                if known_ind in TARGET_INDUSTRIES:
                    if probe_page > new_boundary:
                        logger.info(
                            f"[{svc}] 🔄 업종 경계 확장 감지! P{probe_page} [{known_ind}] "
                            f"(이전 경계 P{new_boundary} → 신규 P{probe_page})"
                        )
                        new_boundary = probe_page
                    continue
                else:
                    logger.info(
                        f"[{svc}] ✋ 업종 경계 확정 | P{probe_page} [{known_ind}] — "
                        f"타깃 마지막 P{new_boundary}까지 스캔"
                    )
                    break
            else:
                # 미확인 페이지 → API 1페이지 호출해 업종 확인
                start_idx = (probe_page - 1) * PAGE_SIZE + 1
                end_idx = probe_page * PAGE_SIZE
                logger.info(
                    f"[{svc}] 🔬 업종 경계 프로브 P{probe_page}/{total_pages} 업종 확인 중..."
                )
                try:
                    rows = await self._fetch_page(start_idx, end_idx)
                    if not rows:
                        logger.info(f"[{svc}] 🔬 P{probe_page} 데이터 없음 → 경계 확정")
                        break
                    first_industry = rows[0].get("INDUTY_CD_NM", "").strip()  # INDUTY_NM → INDUTY_CD_NM
                    first_char = next(
                        (r.get("BSSH_NM", "").strip()[:1] for r in rows if r.get("BSSH_NM", "").strip()),
                        ""
                    )
                    last_char = next(
                        (r.get("BSSH_NM", "").strip()[:1] for r in reversed(rows) if r.get("BSSH_NM", "").strip()),
                        ""
                    )
                    if first_industry:
                        page_industries[str(probe_page)] = first_industry
                    if first_char and last_char:
                        page_labels[str(probe_page)] = f"{first_char}~{last_char}"
                    self.page_scan_repo.upsert_page(
                        svc, probe_page,
                        label=page_labels.get(str(probe_page)),
                        industry=first_industry or None,
                        last_scanned_ts=int(time.time()),
                    )

                    if first_industry in TARGET_INDUSTRIES:
                        logger.info(
                            f"[{svc}] 🔬 P{probe_page} [{first_industry}] → 타깃! "
                            f"경계 P{new_boundary} → P{probe_page}로 확장"
                        )
                        new_boundary = probe_page
                    else:
                        logger.info(
                            f"[{svc}] 🔬 P{probe_page} [{first_industry}] → 스킵 업종. "
                            f"경계 확정: 마지막 타깃 P{new_boundary}"
                        )
                        break
                except Exception as e:
                    logger.error(f"[{svc}] ❌ 업종 경계 프로브 P{probe_page} 오류: {e}")
                    break

        return new_boundary

    async def _run_i2861_oldest_first_scan(self, state: dict, start_time: float) -> list:
        """
        I2861 전용 Oldest First Scan + 업종 경계 인식:
        1. state["last_total_count"]에서 전체 페이지 수(현재 ~953p)를 동적으로 계산.
        2. page_industries에서 확인된 스킵 업종(위탁급식 등) 페이지를 스캔 제외.
        3. 업종 경계 프로브: 마지막 타깃 페이지 이후를 한 장씩 확인해 경계 이동 감지.
        4. Tail Probe: DB 전체 끝 이후 +N페이지 확인 (last_total_count 확장).
        5. 페이지 완료 즉시: scraper 위임 → 상태 저장 → 풍부한 SSE 발행.
        """
        svc = self.service_id

        # ── page_scan_history 테이블에서 로드 ────────────────────────────────
        scan_data = self.page_scan_repo.load_all(svc)
        page_timestamps = scan_data["page_timestamps"]
        page_labels     = scan_data["page_labels"]
        page_industries = scan_data["page_industries"]

        # extra_state는 page_* 제외한 순수 내부 상태만 유지
        extra = state.setdefault("extra_state", {})

        # ── 실제 총 페이지 수 동적 계산 ──────────────────────────────────────
        last_total_count = state.get("last_total_count", 0)
        if last_total_count <= 0:
            logger.warning(f"[{svc}] last_total_count 미확인 → 스캔 스킵 (다음 사이클 재시도)")
            return []

        total_pages = (last_total_count + PAGE_SIZE - 1) // PAGE_SIZE
        now_ts = int(time.time())

        # ── 업종 기반 페이지 분류 ──────────────────────────────────────────
        known_target_set = {int(p) for p, i in page_industries.items() if i in TARGET_INDUSTRIES}
        known_skip_set   = {int(p) for p, i in page_industries.items() if i in SKIP_INDUSTRIES}
        unknown_set      = set(range(1, total_pages + 1)) - known_target_set - known_skip_set

        # target_boundary: page_industries에서 확인된 타깃 업종 마지막 페이지
        # (미확인이면 total_pages 사용 → 전체 스캔으로 자연 발견)
        if known_target_set:
            target_boundary = max(known_target_set)
        else:
            target_boundary = total_pages

        # ── 스캔 후보 풀 구성: 타깃 + 미확인 (알려진 스킵 제외) ────────────
        candidate_set = (known_target_set | unknown_set) & set(range(1, total_pages + 1))

        # ── 전체 페이지 상태 분류 (Oldest-First 우선순위 계산) ────────────
        oldest_pages: list[tuple[int, int]] = []
        fresh_count = 0
        never_scanned = 0
        skipped_industry_count = len(known_skip_set)

        for p in sorted(candidate_set):
            last_ts = page_timestamps.get(str(p), 0)
            elapsed = now_ts - last_ts
            if last_ts == 0:
                never_scanned += 1
                oldest_pages.append((p, elapsed))
            elif elapsed >= STALE_THRESHOLD_SEC:
                oldest_pages.append((p, elapsed))
            else:
                fresh_count += 1

        oldest_pages.sort(key=lambda x: x[1], reverse=True)

        # ── 스캔 대상 결정 ─────────────────────────────────────────────────
        if oldest_pages:
            target_pages = [p for p, _ in oldest_pages]
            logger.info(
                f"[{svc}] 🚀 Oldest First Scan 시작 | 후보 {len(candidate_set)}p "
                f"(⏭ 업종 스킵 {skipped_industry_count}p 제외) | "
                f"🔴 만료 {len(oldest_pages)}p (미스캔 {never_scanned}p 포함) · 🟢 신선 {fresh_count}p"
            )
            logger.info(
                f"[{svc}] → 이번 사이클 스캔 대상: 만료 {len(target_pages)}p 전체"
            )
        else:
            # 전부 신선 → 가장 오래된 1개 롤링
            rolling = sorted(
                [(p, page_timestamps.get(str(p), 0)) for p in candidate_set],
                key=lambda x: x[1]
            )
            target_pages = [rolling[0][0]]
            elapsed_min = (now_ts - rolling[0][1]) // 60
            logger.info(
                f"[{svc}] 🔄 평시 롤링 | 후보 {len(candidate_set)}p 모두 1시간 이내 신선 "
                f"→ 가장 오래된 P{target_pages[0]} 선정 ({elapsed_min}분 경과)"
            )

        # ── Tail Probe: 알려진 마지막 페이지 이후 +N페이지 추가 조회 ──────────
        tail_probe_pages = [total_pages + i for i in range(1, TAIL_PROBE_EXTRA + 1)]
        for tp in tail_probe_pages:
            if tp not in target_pages:
                target_pages.append(tp)
        logger.info(
            f"[{svc}] 🔎 Tail Probe 추가: P{tail_probe_pages[0]}~P{tail_probe_pages[-1]} "
            f"(신규 tail 확장 감지 목적)"
        )

        known_tail_pages = set(range(1, total_pages + 1))

        from app.core.events import broadcaster
        from scraper import run_scraper_for_service_with_rows

        all_rows: list = []
        scanned_success_pages: list[int] = []
        cycle_api_calls = 0
        page_elapsed_times: list[float] = []

        # ── 병렬 스캔 동기화 프리미티브 ─────────────────────────────────────
        n_workers = settings.SCAN_WORKERS
        semaphore   = asyncio.Semaphore(n_workers)   # 동시 워커 수 제한
        db_lock     = asyncio.Lock()                  # SQLite 쓰기 직렬화
        state_lock  = asyncio.Lock()                  # 공유 dict 보호
        counter_lock = asyncio.Lock()                 # 카운터 원자적 갱신
        retry_set: set[int] = set()                   # 1차 실패 페이지 → 2차 재처리
        pages_total = len(target_pages)

        logger.info(
            f"[{svc}] 🔀 병렬 스캔 시작 | 워커 수: {n_workers} | "
            f"대상: {pages_total}p"
        )

        async def _scan_one(page: int, worker_id: int, is_retry: bool = False) -> None:
            nonlocal cycle_api_calls
            start_idx = (page - 1) * PAGE_SIZE + 1
            end_idx   = page * PAGE_SIZE
            is_probe  = page not in known_tail_pages
            probe_tag = " [TAIL PROBE]" if is_probe else ""
            retry_tag = " [재시도]" if is_retry else ""

            async with semaphore:
                logger.info(
                    f"[{svc}] W{worker_id} 📥 P{page}/{total_pages}{probe_tag}{retry_tag} "
                    f"조회 중: {start_idx:,} ~ {end_idx:,}"
                )
                page_fetch_start = time.time()

                # ── I/O: API 조회 (병렬 실행) ────────────────────────────────
                try:
                    rows = await self._fetch_page(start_idx, end_idx)
                except Exception as e:
                    async with counter_lock:
                        cycle_api_calls += 1
                    logger.error(
                        f"[{svc}] W{worker_id} ❌ P{page} Fetch 오류: {e}"
                        + (" → retry_set에 추가" if not is_retry else " → 최종 실패")
                    )
                    if not is_retry:
                        retry_set.add(page)
                    return

                fetch_elapsed = time.time() - page_fetch_start
                row_count = len(rows)

                async with counter_lock:
                    cycle_api_calls += 1
                    page_elapsed_times.append(fetch_elapsed)

                # ── 라벨/업종 추출 → 공유 dict 갱신 (Lock 보호) ──────────────
                if rows:
                    first_char = next(
                        (r.get("BSSH_NM", "").strip()[:1] for r in rows if r.get("BSSH_NM", "").strip()),
                        ""
                    )
                    last_char = next(
                        (r.get("BSSH_NM", "").strip()[:1] for r in reversed(rows) if r.get("BSSH_NM", "").strip()),
                        ""
                    )
                    first_industry = rows[0].get("INDUTY_CD_NM", "").strip()
                    async with state_lock:
                        if first_char and last_char:
                            page_labels[str(page)] = f"{first_char}~{last_char}"
                        if first_industry:
                            page_industries[str(page)] = first_industry

                # ── scraper 파이프라인 (DB 쓰기 Lock 직렬화) ─────────────────
                page_stats = {
                    "total_fetched": row_count,
                    "new_indexed": 0, "skipped_dup": 0,
                    "today": 0, "yesterday": 0,
                    "today_in_page": 0, "yesterday_in_page": 0,
                }
                page_industry = page_industries.get(str(page), "")
                is_skip_page  = page_industry in SKIP_INDUSTRIES

                if rows and not is_skip_page:
                    async with db_lock:
                        result = await run_scraper_for_service_with_rows(
                            svc, rows, collected_by="oldest_first_scan"
                        )
                    page_stats.update({
                        "new_indexed":       result.get("new_indexed", 0),
                        "skipped_dup":       result.get("skipped_dup", 0),
                        "today":             result.get("today", 0),
                        "yesterday":         result.get("yesterday", 0),
                        "today_in_page":     result.get("today_in_page", 0),
                        "yesterday_in_page": result.get("yesterday_in_page", 0),
                    })
                    async with counter_lock:
                        all_rows.extend(rows)
                elif is_skip_page:
                    logger.info(
                        f"[{svc}] W{worker_id} ⏭ P{page} [{page_industry}] — 스킵 업종"
                    )

                # ── Tail Probe: last_total_count 확장 ────────────────────────
                if is_probe and rows:
                    new_total = page * PAGE_SIZE
                    async with state_lock:
                        if new_total > state.get("last_total_count", 0):
                            state["last_total_count"] = new_total
                            new_total_pages = (new_total + PAGE_SIZE - 1) // PAGE_SIZE
                            logger.info(
                                f"[{svc}] W{worker_id} 🆕 Tail 확장 감지! "
                                f"last_total_count 갱신: {new_total:,}건 (P{new_total_pages})"
                            )

                # ── page_scan_history 테이블 저장 (db_lock) ──────────────────
                captured_label    = page_labels.get(str(page))
                captured_industry = page_industries.get(str(page))
                async with db_lock:
                    self.page_scan_repo.upsert_page(
                        svc, page,
                        label=captured_label,
                        industry=captured_industry,
                        last_scanned_ts=int(time.time()),
                    )

                # ── state 저장 (state_lock) ───────────────────────────────────
                async with state_lock:
                    self.state_repo.save_state(svc, state)
                    scanned_success_pages.append(page)

                # ── 완료 로그 ─────────────────────────────────────────────────
                elapsed_so_far = time.time() - start_time
                async with counter_lock:
                    done_so_far = len(scanned_success_pages)
                    remaining = pages_total - done_so_far
                    avg_sec = sum(page_elapsed_times) / len(page_elapsed_times) if page_elapsed_times else fetch_elapsed
                    est_remaining_min = round((remaining * avg_sec) / 60, 1)



        # ── 업종 경계 프로브 (메인 스캔 완료 후 순차 실행) ────────────────
        # page_industries가 어느 정도 채워진 경우에만 실행 (초기 풀스캔 중엔 생략)
        if known_target_set:
            updated_boundary = await self._probe_industry_boundary(
                target_boundary=target_boundary,
                total_pages=total_pages,
                page_industries=page_industries,
                page_labels=page_labels,
                svc=svc,
            )
            if updated_boundary != target_boundary:
                extra["target_boundary_page"] = updated_boundary
                self.state_repo.save_state(svc, state)
                logger.info(
                    f"[{svc}] 📍 target_boundary 갱신: P{target_boundary} → P{updated_boundary} "
                    f"(상태 저장 완료)"
                )
            else:
                logger.info(
                    f"[{svc}] 📍 업종 경계 유지: 타깃 마지막 P{target_boundary} 확정"
                )
        else:
            logger.info(
                f"[{svc}] ℹ️ page_industries 미수집 → 업종 경계 프로브 생략 (초기 풀스캔 중)"
            )

        elapsed_sec = time.time() - start_time
        remaining_stale = len(oldest_pages) - len(target_pages)
        logger.info(
            f"[{svc}] ✔️ Oldest First Scan 완료 | "
            f"이번 사이클: {len(scanned_success_pages)}p 스캔 · API {cycle_api_calls}회 · 소요 {elapsed_sec:.1f}초"
            + (f" | 잔여 만료: {remaining_stale}p → 다음 사이클에 계속" if remaining_stale > 0 else "")
        )
        return all_rows

    async def scan_for_updates(self) -> list:
        """주기적으로 실행되어 Oldest-First Scan을 수행합니다."""
        svc = self.service_id
        start_time = time.time()
        logger.info(f"[{svc}] 🚀 Oldest First Scan 사이클 시작")
        state = self.state_repo.load_state(svc)
        return await self._run_i2861_oldest_first_scan(state, start_time)
