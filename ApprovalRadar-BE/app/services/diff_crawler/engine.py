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
STALE_THRESHOLD_SEC = 3600  # 1시간


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
        1. 전체 5개 페이지의 last_scanned_at 타임스탬프를 점검하여 1시간 초과 페이지를 모두 스캔.
        2. 1시간 초과 페이지가 없으면 가장 오래된 1개 페이지를 순차 롤링.
        3. 페이지 완료 즉시: scraper 파이프라인 위임 → 상태 저장 → 상세 SSE 발행.
        """
        svc = self.service_id
        extra = state.setdefault("extra_state", {})
        page_timestamps = extra.setdefault("page_timestamps", {})
        page_labels = extra.setdefault("page_labels", {})

        now_ts = int(time.time())
        total_pages = 5

        # ── 전체 페이지 상태 점검 ──────────────────────────────────────────
        oldest_pages = []
        fresh_pages = []

        for p in range(1, total_pages + 1):
            last_ts = page_timestamps.get(str(p), 0)
            elapsed = now_ts - last_ts
            elapsed_min = elapsed // 60
            label = page_labels.get(str(p), "—")

            if elapsed >= STALE_THRESHOLD_SEC:
                oldest_pages.append((p, elapsed))
                status = f"🔴 {elapsed_min}분 경과"
            else:
                remaining = (STALE_THRESHOLD_SEC - elapsed) // 60
                fresh_pages.append(p)
                status = f"🟢 {elapsed_min}분 경과 ({remaining}분 후 만료)"

            logger.info(f"[{svc}]   P{p} [{label}] {status}")

        # ── 스캔 대상 결정 ─────────────────────────────────────────────────
        oldest_pages.sort(key=lambda x: x[1], reverse=True)

        if oldest_pages:
            target_pages = [p for p, _ in oldest_pages]
            logger.info(
                f"[{svc}] 🚀 Oldest First Scan — 1시간 초과 {len(target_pages)}개 페이지 전체 스캔: "
                f"{[f'P{p}' for p in target_pages]}"
            )
        else:
            rolling_candidates = sorted(
                [(p, page_timestamps.get(str(p), 0)) for p in range(1, total_pages + 1)],
                key=lambda x: x[1]
            )
            target_pages = [rolling_candidates[0][0]]
            logger.info(
                f"[{svc}] 🔄 평시 롤링 — 전체 페이지 1시간 이내, "
                f"가장 오래된 P{target_pages[0]} 선정"
            )

        from app.core.events import broadcaster
        from scraper import run_scraper_for_service_with_rows

        all_rows = []
        scanned_success_pages = []
        cycle_api_calls = 0
        page_elapsed_times: list[float] = []

        for idx, page in enumerate(target_pages):
            start_idx = (page - 1) * PAGE_SIZE + 1
            end_idx = page * PAGE_SIZE
            pages_total = len(target_pages)
            pages_done = idx  # 이 페이지 완료 전

            logger.info(f"[{svc}] 📥 P{page} 조회 중: {start_idx:,} ~ {end_idx:,}")
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

                # ── scraper 파이프라인 즉시 위임 ────────────────────────────
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

                # ── 타임스탬프 즉시 저장 ──────────────────────────────────────
                page_timestamps[str(page)] = int(time.time())
                state["last_total_count"] = max(state.get("last_total_count", 0), 4800)
                self.state_repo.save_state(svc, state)
                scanned_success_pages.append(page)

                # ── 사이클 메타 계산 ──────────────────────────────────────────
                pages_done_now = idx + 1
                pages_remaining = pages_total - pages_done_now
                elapsed_so_far = time.time() - start_time
                avg_sec = sum(page_elapsed_times) / len(page_elapsed_times)
                est_remaining_sec = pages_remaining * avg_sec
                est_remaining_min = round(est_remaining_sec / 60, 1)

                cycle_info = {
                    "elapsed_sec": round(elapsed_so_far, 1),
                    "api_calls": cycle_api_calls,
                    "pages_done": pages_done_now,
                    "pages_total": pages_total,
                    "est_remaining_min": est_remaining_min,
                }

                logger.info(
                    f"[{svc}] ✅ P{page} 완료 | "
                    f"조회 {row_count:,}건 | "
                    f"오늘 {page_stats['today']}건 · 어제 {page_stats['yesterday']}건 · "
                    f"신규색인 {page_stats['new_indexed']}건 · 미색인 {page_stats['skipped_dup']}건 | "
                    f"소요 {elapsed_so_far:.1f}초 · API {cycle_api_calls}회 · 잔여 ~{est_remaining_min}분"
                )

                # ── 페이지 단위 풍부한 PLAYGROUND_UPDATE SSE 발행 ─────────────
                broadcaster.broadcast_sync(json.dumps({
                    "type": "PLAYGROUND_UPDATE",
                    "page": page,
                    "page_label": page_labels.get(str(page)),
                    "stats": page_stats,
                    "cycle": cycle_info,
                }, ensure_ascii=False))

            except Exception as e:
                cycle_api_calls += 1  # 실패해도 호출은 카운트
                logger.error(f"[{svc}] ❌ P{page} Fetch 오류: {e}")

        elapsed_sec = time.time() - start_time
        logger.info(
            f"[{svc}] ✔️ Oldest First Scan 완료 | "
            f"스캔: {[f'P{p}' for p in scanned_success_pages]} | "
            f"총 조회: {len(all_rows):,}건 · API {cycle_api_calls}회 · 소요: {elapsed_sec:.1f}초"
        )
        return all_rows

    async def scan_for_updates(self) -> list:
        """주기적으로 실행되어 Oldest-First Scan을 수행합니다."""
        svc = self.service_id
        start_time = time.time()
        logger.info(f"[{svc}] 🚀 Oldest First Scan 시작 — 전체 페이지 상태 점검")
        state = self.state_repo.load_state(svc)
        return await self._run_i2861_oldest_first_scan(state, start_time)
