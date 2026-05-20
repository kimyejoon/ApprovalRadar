import asyncio
import random
import time
from app.core.config import settings
from app.clients.foodsafety_api import ApiClient
from app.repositories.state_repository import StateRepository
from app.core.logger import logger

PAGE_SIZE = 1000


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
        2. 임계치(1시간, 3600초) 이상 지났거나 기록이 없는 페이지는 최우선(Oldest) 스캔 대상으로 선정.
        3. 이번 주기에서는 우선순위로 선정된 페이지와 순차적 롤링 대상 페이지를 1~2개 조합하여 스캔 수행.
        4. 스캔 성공 시 타임스탬프를 현재 시각으로 갱신하고, 수집된 데이터를 scraper 파이프라인으로 위임.
        """
        svc = self.service_id
        logger.info(f"[{svc}] 🚀 Oldest First Scan 시작...")

        extra = state.setdefault("extra_state", {})
        page_timestamps = extra.setdefault("page_timestamps", {})

        now_ts = int(time.time())
        total_pages = 5  # I2861 라이브 데이터 기준 약 4,800건이므로 5페이지

        # 각 페이지별 경과 시간 확인
        oldest_pages = []
        for p in range(1, total_pages + 1):
            p_str = str(p)
            last_scanned = page_timestamps.get(p_str, 0)
            elapsed = now_ts - last_scanned
            if elapsed >= 3600:
                oldest_pages.append((p, elapsed))

        # 가장 오래된 페이지 정렬
        oldest_pages.sort(key=lambda x: x[1], reverse=True)
        
        target_pages = []
        if oldest_pages:
            # 1시간 초과된 페이지 우선 (최대 2개 페이지 스캔)
            target_pages = [p for p, _ in oldest_pages[:2]]
            logger.info(
                f"[{svc}] 🕐 마지막 스캔 후 1시간 초과된 Oldest 페이지 발견 → 스캔 선정: "
                f"{[f'P{p}' for p in target_pages]}"
            )
        else:
            # 1시간 초과가 없으면 가장 마지막 조회 시각이 오랜 순서대로 1개 롤링
            rolling_candidates = []
            for p in range(1, total_pages + 1):
                rolling_candidates.append((p, page_timestamps.get(str(p), 0)))
            rolling_candidates.sort(key=lambda x: x[1])
            target_pages = [rolling_candidates[0][0]]
            logger.info(f"[{svc}] 🎯 평시 롤링 스캔 페이지 선정: P{target_pages[0]}")

        # 상호명 대역 저장용 딕셔너리
        page_labels = extra.setdefault("page_labels", {})

        import json
        from app.core.events import broadcaster

        new_data_rows = []
        scanned_success_pages = []

        for page in target_pages:
            start_idx = (page - 1) * PAGE_SIZE + 1
            end_idx = page * PAGE_SIZE

            logger.info(f"[{svc}] 📥 페이지 {page} 조회 중: {start_idx:,} ~ {end_idx:,}")
            try:
                rows = await self._fetch_page(start_idx, end_idx)
                if rows:
                    new_data_rows.extend(rows)
                    # 첫 번째 및 마지막 레코드의 상호명 첫 글자 추출
                    first_nm = rows[0].get("BSSH_NM", "").strip()
                    last_nm = rows[-1].get("BSSH_NM", "").strip()
                    first_char = first_nm[0] if first_nm else ""
                    last_char = last_nm[0] if last_nm else ""
                    if first_char and last_char:
                        page_labels[str(page)] = f"{first_char}~{last_char}"

                    # ── 페이지 스캔 완료 즉시: scraper 파이프라인 → 상태 저장 → SSE 발행 ──
                    from scraper import run_scraper_for_service_with_rows
                    await run_scraper_for_service_with_rows(svc, rows, collected_by="rolling_scan")

                # 성공 여부와 무관하게 타임스탬프 갱신 (Fetch 자체가 성공했으므로)
                page_timestamps[str(page)] = int(time.time())
                state["last_total_count"] = max(state.get("last_total_count", 0), 4800)
                self.state_repo.save_state(svc, state)

                scanned_success_pages.append(page)
                logger.info(f"[{svc}] ✅ P{page} 상태 저장 완료 → PLAYGROUND_UPDATE 발행")

                # 페이지 단위 즉시 SSE 브로드캐스트
                broadcaster.broadcast_sync(
                    json.dumps({"type": "PLAYGROUND_UPDATE"}, ensure_ascii=False)
                )

            except Exception as e:
                logger.error(f"[{svc}] ❌ 페이지 {page} Fetch 오류: {e}")

        elapsed_sec = time.time() - start_time
        logger.info(
            f"[{svc}] ✔️ Oldest First Scan 완료. "
            f"성공: {[f'P{p}' for p in scanned_success_pages]} | "
            f"신규 획득: {len(new_data_rows):,}건 | "
            f"소요시간: {elapsed_sec:.1f}초"
        )
        return new_data_rows

    async def scan_for_updates(self) -> list:
        """주기적으로 실행되어 차분(Delta)을 감지합니다."""
        svc = self.service_id
        start_time = time.time()
        state = self.state_repo.load_state(svc)
        return await self._run_i2861_oldest_first_scan(state, start_time)
