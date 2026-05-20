import asyncio
import random
import time
import json
import datetime
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger

PAGE_SIZE = 1000
STALE_THRESHOLD_SEC = 3600   # 1시간
# 한 사이클에서 스캔할 최대 페이지 수 (API 비용 제어)
MAX_PAGES_PER_CYCLE = 200
# 알려진 마지막 페이지 이후 추가 조회할 Tail Probe 페이지 수 (신규 데이터 유입 감지)
TAIL_PROBE_EXTRA = 3


class DiffCrawlerEngine:
    def __init__(self, api_client: ApiClient, service_id: str):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = StateRepository()

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

    async def _run_i2861_oldest_first_scan(self, state: dict, start_time: float) -> list:
        """
        I2861 전용 Oldest First Scan:
        1. state["last_total_count"]에서 전체 페이지 수(현재 ~953p)를 동적으로 계산.
        2. page_timestamps에서 각 페이지의 마지막 스캔 시각을 관리.
        3. 1시간 초과 페이지를 오래된 순서로 최대 MAX_PAGES_PER_CYCLE개 스캔.
        4. 1시간 초과 없으면 가장 오래된 1개 페이지를 롤링 스캔.
        5. 페이지 완료 즉시: scraper 위임 → 상태 저장 → 풍부한 SSE 발행.
        """
        svc = self.service_id
        extra = state.setdefault("extra_state", {})
        page_timestamps = extra.setdefault("page_timestamps", {})
        page_labels = extra.setdefault("page_labels", {})

        # ── 실제 총 페이지 수 동적 계산 ──────────────────────────────────────
        last_total_count = state.get("last_total_count", 0)
        if last_total_count <= 0:
            logger.warning(f"[{svc}] last_total_count 미확인 → 스캔 스킵 (다음 사이클 재시도)")
            return []

        total_pages = (last_total_count + PAGE_SIZE - 1) // PAGE_SIZE
        now_ts = int(time.time())

        # ── 전체 페이지 상태 분류 ──────────────────────────────────────────
        oldest_pages: list[tuple[int, int]] = []   # (page, elapsed_sec)
        fresh_count = 0
        never_scanned = 0

        for p in range(1, total_pages + 1):
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
            # 1시간 초과 페이지들 중 이번 사이클 처리 가능한 최대치까지
            target_pages = [p for p, _ in oldest_pages[:MAX_PAGES_PER_CYCLE]]
            logger.info(
                f"[{svc}] 🚀 Oldest First Scan 시작 | 전체 {total_pages}p 중 "
                f"🔴 만료 {len(oldest_pages)}p (미스캔 {never_scanned}p 포함) "
                f"· 🟢 신선 {fresh_count}p"
            )
            logger.info(
                f"[{svc}] → 이번 사이클 스캔 대상: {len(target_pages)}p "
                f"(P{target_pages[0]}~P{target_pages[-1]}, 최대 {MAX_PAGES_PER_CYCLE}p 제한)"
            )
        else:
            # 전부 신선 → 가장 오래된 1개 롤링
            rolling = sorted(
                [(p, page_timestamps.get(str(p), 0)) for p in range(1, total_pages + 1)],
                key=lambda x: x[1]
            )
            target_pages = [rolling[0][0]]
            elapsed_min = (now_ts - rolling[0][1]) // 60
            logger.info(
                f"[{svc}] 🔄 평시 롤링 | 전체 {total_pages}p 모두 1시간 이내 신선 "
                f"→ 가장 오래된 P{target_pages[0]} 선정 ({elapsed_min}분 경과)"
            )

        # ── Tail Probe: 알려진 마지막 페이지 이후 +N페이지 추가 조회 ──────────
        # 매 사이클마다 신규 데이터 유입(tail 확장) 여부를 탐지하기 위해 실행
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

        for idx, page in enumerate(target_pages):
            start_idx = (page - 1) * PAGE_SIZE + 1
            end_idx = page * PAGE_SIZE
            pages_total = len(target_pages)

            is_probe = page not in known_tail_pages
            probe_tag = " [TAIL PROBE]" if is_probe else ""
            logger.info(f"[{svc}] 📥 P{page}/{total_pages}{probe_tag} 조회 중: {start_idx:,} ~ {end_idx:,}")
            page_fetch_start = time.time()

            try:
                rows = await self._fetch_page(start_idx, end_idx)
                cycle_api_calls += 1
                page_elapsed_times.append(time.time() - page_fetch_start)
                row_count = len(rows)

                # 상호명 대역 추출
                if rows:
                    first_char = rows[0].get("BSSH_NM", "").strip()[:1]
                    last_char = rows[-1].get("BSSH_NM", "").strip()[:1]
                    if first_char and last_char:
                        page_labels[str(page)] = f"{first_char}~{last_char}"

                # ── scraper 파이프라인 즉시 위임 ──────────────────────────────
                page_stats = {
                    "total_fetched": row_count,
                    "new_indexed": 0,
                    "skipped_dup": 0,
                    "today": 0,
                    "yesterday": 0,
                }
                if rows:
                    result = await run_scraper_for_service_with_rows(
                        svc, rows, collected_by="oldest_first_scan"
                    )
                    page_stats.update({
                        "new_indexed": result.get("new_indexed", 0),
                        "skipped_dup": result.get("skipped_dup", 0),
                        "today": result.get("today", 0),
                        "yesterday": result.get("yesterday", 0),
                    })
                    all_rows.extend(rows)

                    # ── Tail Probe 페이지에 데이터 유입 감지 → last_total_count 확장 ────────
                    if is_probe:
                        new_total = page * PAGE_SIZE
                        if new_total > state.get("last_total_count", 0):
                            state["last_total_count"] = new_total
                            new_total_pages = (new_total + PAGE_SIZE - 1) // PAGE_SIZE
                            logger.info(
                                f"[{svc}] 🆕 Tail 확장 감지! "
                                f"last_total_count 갱신: {new_total:,}건 (P{new_total_pages})"
                            )

                # ── 타임스탬프 즉시 저장 ──────────────────────────────────────
                page_timestamps[str(page)] = int(time.time())
                self.state_repo.save_state(svc, state)
                scanned_success_pages.append(page)

                # ── 사이클 메타 계산 ──────────────────────────────────────────
                pages_done_now = idx + 1
                pages_remaining = pages_total - pages_done_now
                elapsed_so_far = time.time() - start_time
                avg_sec = sum(page_elapsed_times) / len(page_elapsed_times)
                est_remaining_min = round((pages_remaining * avg_sec) / 60, 1)

                cycle_info = {
                    "elapsed_sec": round(elapsed_so_far, 1),
                    "api_calls": cycle_api_calls,
                    "pages_done": pages_done_now,
                    "pages_total": pages_total,
                    "est_remaining_min": est_remaining_min,
                }

                logger.info(
                    f"[{svc}] ✅ P{page}/{total_pages} 완료 | "
                    f"조회 {row_count:,}건 | "
                    f"오늘 {page_stats['today']}건 · 어제 {page_stats['yesterday']}건 · "
                    f"신규 {page_stats['new_indexed']}건 · 중복 {page_stats['skipped_dup']}건 | "
                    f"소요 {elapsed_so_far:.1f}초 · API {cycle_api_calls}회 · 잔여 ~{est_remaining_min}분"
                )

                # ── 페이지 단위 풍부한 PLAYGROUND_UPDATE SSE 발행 ────────────
                broadcaster.broadcast_sync(json.dumps({
                    "type": "PLAYGROUND_UPDATE",
                    "page": page,
                    "page_label": page_labels.get(str(page)),
                    "stats": page_stats,
                    "cycle": cycle_info,
                }, ensure_ascii=False))

            except Exception as e:
                cycle_api_calls += 1
                logger.error(f"[{svc}] ❌ P{page} Fetch 오류: {e}")

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
