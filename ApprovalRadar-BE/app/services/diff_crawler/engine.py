import asyncio
import random
import time
import json
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
        1. 전체 5개 페이지(총 ~4,800여건)에 대하여 각 페이지의 last_scanned_at 타임스탬프를 관리.
        2. 임계치(1시간) 이상 지났거나 기록이 없는 페이지는 모두 즉시 스캔.
        3. 1시간 초과 페이지가 없으면 가장 오래된 1개 페이지를 순차 롤링.
        4. 스캔 완료 즉시 페이지 단위로 타임스탬프 갱신 + scraper 파이프라인 위임 + SSE 발행.
        """
        svc = self.service_id
        extra = state.setdefault("extra_state", {})
        page_timestamps = extra.setdefault("page_timestamps", {})
        page_labels = extra.setdefault("page_labels", {})

        now_ts = int(time.time())
        total_pages = 5  # I2861 라이브 데이터 기준 약 4,800건이므로 5페이지

        # ── 전체 페이지 상태 분류 ──────────────────────────────────────────
        oldest_pages = []   # 1시간 초과
        fresh_pages = []    # 1시간 이내

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

        # ── 스캔 대상 결정 ────────────────────────────────────────────────
        oldest_pages.sort(key=lambda x: x[1], reverse=True)

        if oldest_pages:
            target_pages = [p for p, _ in oldest_pages]
            logger.info(
                f"[{svc}] 🚀 Oldest First Scan — 1시간 초과 {len(target_pages)}개 페이지 전체 스캔: "
                f"{[f'P{p}' for p in target_pages]}"
            )
        else:
            # 1시간 초과 없음 → 가장 오래된 1개 롤링
            rolling_candidates = sorted(
                [(p, page_timestamps.get(str(p), 0)) for p in range(1, total_pages + 1)],
                key=lambda x: x[1]
            )
            target_pages = [rolling_candidates[0][0]]
            logger.info(
                f"[{svc}] 🔄 평시 롤링 — 전체 페이지 1시간 이내, "
                f"가장 오래된 P{target_pages[0]} 선정"
            )

        # ── 페이지 순차 스캔 ──────────────────────────────────────────────
        from app.core.events import broadcaster

        all_rows = []
        scanned_success_pages = []

        for page in target_pages:
            start_idx = (page - 1) * PAGE_SIZE + 1
            end_idx = page * PAGE_SIZE

            logger.info(f"[{svc}] 📥 P{page} 조회 중: {start_idx:,} ~ {end_idx:,}")
            try:
                rows = await self._fetch_page(start_idx, end_idx)
                row_count = len(rows)

                if rows:
                    all_rows.extend(rows)
                    # 상호명 대역 추출
                    first_char = rows[0].get("BSSH_NM", "").strip()[:1]
                    last_char = rows[-1].get("BSSH_NM", "").strip()[:1]
                    if first_char and last_char:
                        page_labels[str(page)] = f"{first_char}~{last_char}"

                    # 즉시 scraper 파이프라인 위임
                    from scraper import run_scraper_for_service_with_rows
                    await run_scraper_for_service_with_rows(svc, rows, collected_by="oldest_first_scan")

                # 타임스탬프 즉시 갱신 + 상태 저장
                page_timestamps[str(page)] = int(time.time())
                state["last_total_count"] = max(state.get("last_total_count", 0), 4800)
                self.state_repo.save_state(svc, state)

                scanned_success_pages.append(page)
                logger.info(
                    f"[{svc}] ✅ P{page} 완료: 조회 {row_count:,}건 → 저장 완료, PLAYGROUND_UPDATE 발행"
                )

                # 페이지 단위 즉시 SSE 브로드캐스트
                broadcaster.broadcast_sync(
                    json.dumps({"type": "PLAYGROUND_UPDATE"}, ensure_ascii=False)
                )

            except Exception as e:
                logger.error(f"[{svc}] ❌ P{page} Fetch 오류: {e}")

        elapsed_sec = time.time() - start_time
        logger.info(
            f"[{svc}] ✔️ Oldest First Scan 완료 | "
            f"스캔: {[f'P{p}' for p in scanned_success_pages]} | "
            f"총 조회: {len(all_rows):,}건 | "
            f"소요: {elapsed_sec:.1f}초"
        )
        return all_rows

    async def scan_for_updates(self) -> list:
        """주기적으로 실행되어 Oldest-First Scan을 수행합니다."""
        svc = self.service_id
        start_time = time.time()
        logger.info(f"[{svc}] 🚀 Oldest First Scan 시작 — 전체 페이지 상태 점검")
        state = self.state_repo.load_state(svc)
        return await self._run_i2861_oldest_first_scan(state, start_time)
