import asyncio
import time
from datetime import datetime, timedelta
from typing import Literal

from app.core.logger import logger
from app.services.smart_sweep.result import SweepResult
from app.services.smart_sweep.cache import (
    _load_cache, _save_cache, _batch_save_cache, _save_log
)

SVC_ID = "I2861"
SEG_SIZE = 1000           # 세그먼트당 인덱스 범위
PROBE_STRATA = 10         # stratified 탐침 구간 수
MAX_INDEX = 1_000_000     # 탐침 대상 최대 인덱스
WARM_DAYS_AGO = 2         # WARM 판단 기준: N일 이내

SegClass = Literal["HOT", "WARM", "COLD"]

class SmartSweepService:
    def __init__(self, api_client):
        self.api_client = api_client

    def get_stratified_probes(self, n: int = PROBE_STRATA) -> list[tuple[int, int]]:
        """전체 인덱스 공간을 n개로 균등 분할하여 대표 세그먼트 반환."""
        step = MAX_INDEX // n
        probes = []
        for i in range(n):
            start = i * step + 1
            end = start + SEG_SIZE - 1
            probes.append((start, end))
        return probes

    def classify(self, first_chng: str) -> SegClass:
        """first_CHNG 기준으로 HOT/WARM/COLD 분류."""
        today = datetime.now().strftime("%Y%m%d")
        warm_threshold = (datetime.now() - timedelta(days=WARM_DAYS_AGO)).strftime("%Y%m%d")

        if first_chng and first_chng >= today:
            return "HOT"
        if first_chng and first_chng >= warm_threshold:
            return "WARM"
        return "COLD"

    async def _fetch_seg(self, seg_start: int, seg_end: int) -> dict | None:
        """
        단일 세그먼트 조회.
        """
        try:
            data = await self.api_client.fetch_data(
                SVC_ID, seg_start, seg_end, max_retries=1, timeout=8
            )
            if not data or SVC_ID not in data:
                return None
            block = data[SVC_ID]
            code = block.get("RESULT", {}).get("CODE", "")
            if code not in ("INFO-000", "INFO-200"):
                return None
            rows = block.get("row", [])
            total_str = block.get("total_count", "0")
            total = int(total_str) if str(total_str).isdigit() else 0
            first_chng = rows[0].get("CHNG_DT", "") if rows else ""
            return {"total": total, "first_chng": first_chng, "rows": rows, "code": code}
        except Exception as e:
            logger.debug(f"[SmartSweep] {seg_start}/{seg_end} 조회 스킵: {e}")
            return None

    async def run_micro_probe(self) -> SweepResult:
        """
        Stratified 10개 탐침 → HOT/DELTA 분류.
        """
        from app.core.scheduler import _scraper_lock
        if _scraper_lock.locked():
            logger.info("[SmartSweep] ⏭️ 메인 스캐너 실행 중 → Micro Probe 스킵 (API 경합 방지)")
            return SweepResult()

        result = SweepResult()
        result.strategy = "micro_probe"
        t0 = time.time()

        probes = self.get_stratified_probes(PROBE_STRATA)

        logger.info(f"[SmartSweep] 🔍 Micro Probe 시작: {len(probes)}개 탐침")

        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        for seg_start, seg_end in probes:
            if _scraper_lock.locked():
                logger.info("[SmartSweep] ⏭️ 메인 스캐너 시작됨 → 탐침 중단")
                break

            seg_data = await self._fetch_seg(seg_start, seg_end)
            result.probe_calls += 1
            await asyncio.sleep(1.2)  # WAF 경합 방지

            if seg_data is None:
                logger.info(f"[SmartSweep] ⚠ {seg_start:,}~{seg_end:,} 스킵 (타임아웃/오류)")
                continue

            first_chng = seg_data["first_chng"]
            cls = self.classify(first_chng)

            seg_info = {
                "seg_start": seg_start, "seg_end": seg_end,
                "first_chng": first_chng, "cls": cls,
                "rows": seg_data.get("rows", []),
            }
            result.segments.append(seg_info)

            label = {"HOT": "🎯", "WARM": "📅", "COLD": "❄️"}.get(cls, "")
            logger.info(
                f"[SmartSweep] {label} [{cls}] {seg_start:,}~{seg_end:,} | "
                f"first_CHNG={first_chng}"
            )

            if cls == "HOT":
                result.hot_segs.append(seg_info)

        _batch_save_cache(result.segments, "stratified")

        if not _scraper_lock.locked():
            for seg in result.hot_segs:
                n = await self._collect_segment(seg, today, yesterday)
                result.collected += n
                result.probe_calls += 1

        result.elapsed_sec = time.time() - t0
        _save_log(result)

        logger.info(
            f"[SmartSweep] ✅ Micro Probe 완료: "
            f"{result.probe_calls}calls | HOT:{len(result.hot_segs)} "
            f"수집:{result.collected}건 | {result.elapsed_sec:.1f}초"
        )
        return result

    async def run_full_sweep(self, max_segs: int = 1000) -> SweepResult:
        """
        전체 세그먼트 순차 스윕. first_CHNG로 빠른 필터링.
        """
        result = SweepResult()
        result.strategy = "full_sweep"
        t0 = time.time()

        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        probes = [(i * SEG_SIZE + 1, (i + 1) * SEG_SIZE) for i in range(max_segs)]

        logger.info(f"[SmartSweep] 🔄 Full Sweep 시작: 최대 {max_segs}개 세그먼트")

        consecutive_empty = 0
        for seg_start, seg_end in probes:
            if consecutive_empty >= 3:
                logger.info(f"[SmartSweep] 빈 세그먼트 3회 연속 → 탐색 종료")
                break

            seg_data = await self._fetch_seg(seg_start, seg_end)
            result.probe_calls += 1
            await asyncio.sleep(0.4)

            if seg_data is None or seg_data.get("code") == "INFO-200":
                consecutive_empty += 1
                continue

            consecutive_empty = 0
            first_chng = seg_data["first_chng"]
            cls = self.classify(first_chng)

            seg_info = {
                "seg_start": seg_start, "seg_end": seg_end,
                "first_chng": first_chng, "cls": cls,
                "rows": seg_data.get("rows", []),
            }
            result.segments.append(seg_info)

            if cls in ("HOT", "WARM"):
                label = {"HOT": "🎯", "WARM": "📅"}.get(cls, "")
                logger.info(
                    f"[SmartSweep] {label} [{cls}] {seg_start:,}~{seg_end:,} | "
                    f"first_CHNG={first_chng}"
                )
                if cls == "HOT":
                    result.hot_segs.append(seg_info)
                    n = await self._collect_segment(seg_info, today, yesterday)
                    result.collected += n
                    result.probe_calls += 1

        _batch_save_cache(result.segments, "full_sweep")

        result.elapsed_sec = time.time() - t0
        _save_log(result)

        logger.info(
            f"[SmartSweep] ✅ Full Sweep 완료: "
            f"{result.probe_calls}calls | HOT:{len(result.hot_segs)} "
            f"수집:{result.collected}건 | {result.elapsed_sec:.1f}초"
        )
        return result

    async def _collect_segment(self, seg_info: dict, today: str, yesterday: str) -> int:
        """
        세그먼트 rows에서 오늘/어제 CHNG_DT 행만 추출 → DB write.
        """
        rows = seg_info.get("rows", [])
        seg_start = seg_info["seg_start"]
        seg_end = seg_info["seg_end"]

        if not rows:
            seg_data = await self._fetch_seg(seg_start, seg_end)
            if not seg_data:
                return 0
            rows = seg_data.get("rows", [])

        target_rows = [r for r in rows if r.get("CHNG_DT", "") in (today, yesterday)]
        if not target_rows:
            return 0

        logger.info(
            f"[SmartSweep] 📥 {seg_start:,}~{seg_end:,}: "
            f"오늘/어제 {len(target_rows)}건 수집 시도"
        )

        try:
            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows(
                SVC_ID, target_rows, collected_by="smart_sweep"
            )
            return len(target_rows)
        except Exception as e:
            logger.warning(f"[SmartSweep] collect 실패 ({seg_start}~{seg_end}): {e}")
            return 0
