"""
SmartSweep 서비스 — 복합 변경 감지 (Playground 실험용)

전략:
  1. Stratified Probe  — 전체 인덱스 공간을 N구간으로 균등 분할, 각 구간 탐침
  2. first_CHNG 필터  — 첫 행 CHNG_DT가 어제/오늘이면 HOT 세그먼트
  3. total_count 델타 — 캐시 대비 total 변화 세그먼트는 DELTA 분류
  4. 수집              — HOT/DELTA 세그먼트만 rows 조회 → CHNG_DT 필터 → DB write

기존 메인 로직(RollingScanner, DiffCrawler) 무수정.
"""
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Literal

from app.core.logger import logger
from database import get_db

SVC_ID = "I2861"
SEG_SIZE = 1000           # 세그먼트당 인덱스 범위
PROBE_STRATA = 10         # stratified 탐침 구간 수
MAX_INDEX = 1_000_000     # 탐침 대상 최대 인덱스
# first_CHNG 임계값: 이 이상이면 WARM/HOT 판단 (보수적 2일 여유)
WARM_DAYS_AGO = 2

SegClass = Literal["HOT", "WARM", "DELTA", "COLD"]


class SweepResult:
    def __init__(self):
        self.strategy: str = ""
        self.probe_calls: int = 0
        self.segments: list[dict] = []      # 탐침 결과 전체
        self.hot_segs: list[dict] = []      # HOT 세그먼트
        self.delta_segs: list[dict] = []    # DELTA 세그먼트
        self.collected: int = 0
        self.elapsed_sec: float = 0.0
        self.run_at: str = datetime.now().isoformat()

    def to_log_row(self) -> dict:
        return {
            "run_at": self.run_at,
            "strategy": self.strategy,
            "probe_calls": self.probe_calls,
            "hot_segs": len(self.hot_segs),
            "delta_segs": len(self.delta_segs),
            "collected": self.collected,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "detail_json": json.dumps(
                [{"seg": f"{s['seg_start']}/{s['seg_end']}", "class": s["cls"],
                  "total": s.get("total"), "first_chng": s.get("first_chng"),
                  "delta": s.get("delta")}
                 for s in self.segments if s.get("cls") != "COLD"],
                ensure_ascii=False
            ),
        }


class SmartSweepService:
    def __init__(self, api_client):
        self.api_client = api_client

    # ── 탐침 구간 생성 ────────────────────────────────────────────────────────

    def get_stratified_probes(self, n: int = PROBE_STRATA) -> list[tuple[int, int]]:
        """전체 인덱스 공간을 n개로 균등 분할하여 대표 세그먼트 반환."""
        step = MAX_INDEX // n
        probes = []
        for i in range(n):
            start = i * step + 1
            end = start + SEG_SIZE - 1
            probes.append((start, end))
        return probes

    # ── 분류 로직 ─────────────────────────────────────────────────────────────

    def classify(self, total: int, first_chng: str, cached_total: int | None) -> SegClass:
        """세그먼트를 HOT/WARM/DELTA/COLD로 분류."""
        today = datetime.now().strftime("%Y%m%d")
        warm_threshold = (datetime.now() - timedelta(days=WARM_DAYS_AGO)).strftime("%Y%m%d")

        if first_chng and first_chng >= today:
            return "HOT"
        if first_chng and first_chng >= warm_threshold:
            return "WARM"
        if cached_total is not None and total != cached_total:
            return "DELTA"
        return "COLD"

    # ── API 조회 (비동기) ─────────────────────────────────────────────────────

    async def _fetch_seg(self, seg_start: int, seg_end: int) -> dict | None:
        """
        단일 세그먼트 조회. (total_count, first_chng, rows) 반환.
        타임아웃 시 재시도 없이 즉시 None 반환 → 메인 스캐너와 API 경합 방지.
        """
        try:
            # max_retries=1: 타임아웃/오류 시 재시도 없이 즉시 스킵
            # timeout=8: 메인 스캐너의 20초보다 짧게 → SmartSweep이 우선 양보
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

    # ── 캐시 I/O ─────────────────────────────────────────────────────────────

    def _load_cache(self, probes: list[tuple[int, int]]) -> dict[tuple[int, int], int | None]:
        """세그먼트별 이전 total_count를 DB에서 로드."""
        result = {}
        if not probes:
            return result
        with get_db() as conn:
            for seg_start, seg_end in probes:
                row = conn.execute(
                    "SELECT total_count FROM smart_sweep_cache WHERE seg_start=? AND seg_end=?",
                    (seg_start, seg_end)
                ).fetchone()
                result[(seg_start, seg_end)] = row["total_count"] if row else None
        return result

    def _save_cache(self, seg_start: int, seg_end: int, total: int, first_chng: str, label: str):
        with get_db() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO smart_sweep_cache
                   (seg_start, seg_end, total_count, first_chng, probed_at, probe_label)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (seg_start, seg_end, total, first_chng, datetime.now().isoformat(), label)
            )

    def _batch_save_cache(self, entries: list[dict], label: str):
        """여러 세그먼트 캐시를 1회 트랜잭션으로 일괄 저장 (WAL 누적 방지)."""
        if not entries:
            return
        now = datetime.now().isoformat()
        rows = [
            (e["seg_start"], e["seg_end"], e["total"], e["first_chng"], now, label)
            for e in entries
        ]
        with get_db() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO smart_sweep_cache
                   (seg_start, seg_end, total_count, first_chng, probed_at, probe_label)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows
            )

    def _save_log(self, result: SweepResult):
        row = result.to_log_row()
        with get_db() as conn:
            conn.execute(
                """INSERT INTO smart_sweep_log
                   (run_at, strategy, probe_calls, hot_segs, delta_segs, collected, elapsed_sec, detail_json)
                   VALUES (:run_at,:strategy,:probe_calls,:hot_segs,:delta_segs,:collected,:elapsed_sec,:detail_json)""",
                row
            )

    # ── Phase 1: Micro Probe (10개 탐침) ─────────────────────────────────────

    async def run_micro_probe(self) -> SweepResult:
        """
        Stratified 10개 탐침 → HOT/DELTA 분류.
        메인 스캐너(Oldest-First) 실행 중이면 API 경합 방지를 위해 skip.
        API 비용: 탐침 10 + collect × hit_count
        """
        # ── 메인 스캐너 실행 중이면 양보 ─────────────────────────────────────
        from app.core.scheduler import _scraper_lock
        if _scraper_lock.locked():
            logger.info("[SmartSweep] ⏭️ 메인 스캐너 실행 중 → Micro Probe 스킵 (API 경합 방지)")
            return SweepResult()

        result = SweepResult()
        result.strategy = "micro_probe"
        t0 = time.time()

        probes = self.get_stratified_probes(PROBE_STRATA)
        cache = self._load_cache(probes)

        logger.info(f"[SmartSweep] 🔍 Micro Probe 시작: {len(probes)}개 탐침")

        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        for seg_start, seg_end in probes:
            # 탐침 도중 메인 스캐너가 시작되면 즉시 중단
            if _scraper_lock.locked():
                logger.info("[SmartSweep] ⏭️ 메인 스캐너 시작됨 → 탐침 중단")
                break

            seg_data = await self._fetch_seg(seg_start, seg_end)
            result.probe_calls += 1
            await asyncio.sleep(1.2)  # WAF 경합 방지

            if seg_data is None:
                logger.info(f"[SmartSweep] ⚠ {seg_start:,}~{seg_end:,} 스킵 (타임아웃/오류)")
                continue

            total = seg_data["total"]
            first_chng = seg_data["first_chng"]
            cached_total = cache.get((seg_start, seg_end))
            delta = (total - cached_total) if cached_total is not None else None
            cls = self.classify(total, first_chng, cached_total)

            seg_info = {
                "seg_start": seg_start, "seg_end": seg_end,
                "total": total, "first_chng": first_chng,
                "cached_total": cached_total, "delta": delta, "cls": cls,
                "rows": seg_data.get("rows", []),
            }
            result.segments.append(seg_info)
            # ← _save_cache 개별 호출 제거 (배치로 대체)

            label = {"HOT": "🎯", "WARM": "📅", "DELTA": "📈", "COLD": "❄️"}.get(cls, "")
            logger.info(
                f"[SmartSweep] {label} [{cls}] {seg_start:,}~{seg_end:,} | "
                f"total={total} first_CHNG={first_chng} delta={delta}"
            )

            if cls == "HOT":
                result.hot_segs.append(seg_info)
            elif cls == "DELTA":
                result.delta_segs.append(seg_info)

        # 루프 완료 후 1회 배치 저장 (10 write → 1 write, WAL 누적 방지)
        self._batch_save_cache(result.segments, "stratified")

        # HOT/DELTA 세그먼트 collect (메인 스캐너 유휴 시에만)
        if not _scraper_lock.locked():
            for seg in result.hot_segs + result.delta_segs:
                n = await self._collect_segment(seg, today, yesterday)
                result.collected += n
                result.probe_calls += 1

        result.elapsed_sec = time.time() - t0
        self._save_log(result)

        logger.info(
            f"[SmartSweep] ✅ Micro Probe 완료: "
            f"{result.probe_calls}calls | HOT:{len(result.hot_segs)} DELTA:{len(result.delta_segs)} "
            f"수집:{result.collected}건 | {result.elapsed_sec:.1f}초"
        )
        return result

    # ── Phase 2: Full Sweep (전체 세그먼트) ──────────────────────────────────

    async def run_full_sweep(self, max_segs: int = 1000) -> SweepResult:
        """
        전체 세그먼트 순차 스윕. first_CHNG로 빠른 필터링.
        API 비용: max_segs + collect × hit_count
        """
        result = SweepResult()
        result.strategy = "full_sweep"
        t0 = time.time()

        today = datetime.now().strftime("%Y%m%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        probes = [(i * SEG_SIZE + 1, (i + 1) * SEG_SIZE) for i in range(max_segs)]
        cache = self._load_cache(probes)

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
            total = seg_data["total"]
            first_chng = seg_data["first_chng"]
            cached_total = cache.get((seg_start, seg_end))
            delta = (total - cached_total) if cached_total is not None else None
            cls = self.classify(total, first_chng, cached_total)

            seg_info = {
                "seg_start": seg_start, "seg_end": seg_end,
                "total": total, "first_chng": first_chng,
                "cached_total": cached_total, "delta": delta, "cls": cls,
                "rows": seg_data.get("rows", []),
            }
            result.segments.append(seg_info)
            # ← _save_cache 개별 호출 제거 (배치로 대체)

            if cls in ("HOT", "WARM", "DELTA"):
                label = {"HOT": "🎯", "WARM": "📅", "DELTA": "📈"}.get(cls, "")
                logger.info(
                    f"[SmartSweep] {label} [{cls}] {seg_start:,}~{seg_end:,} | "
                    f"first_CHNG={first_chng} delta={delta}"
                )
                if cls in ("HOT", "DELTA"):
                    result.hot_segs.append(seg_info)
                    n = await self._collect_segment(seg_info, today, yesterday)
                    result.collected += n
                    result.probe_calls += 1

        # 루프 완료 후 1회 배치 저장
        self._batch_save_cache(result.segments, "full_sweep")

        result.elapsed_sec = time.time() - t0
        self._save_log(result)

        logger.info(
            f"[SmartSweep] ✅ Full Sweep 완료: "
            f"{result.probe_calls}calls | HOT:{len(result.hot_segs)} "
            f"수집:{result.collected}건 | {result.elapsed_sec:.1f}초"
        )
        return result

    # ── Collect: HOT/DELTA 세그먼트 rows 수집 ───────────────────────────────

    async def _collect_segment(self, seg_info: dict, today: str, yesterday: str) -> int:
        """
        세그먼트 rows에서 오늘/어제 CHNG_DT 행만 추출 → DB write.
        이미 rows가 있으면 재조회 없이 재사용. total > SEG_SIZE면 추가 조회 불필요
        (API가 최신 SEG_SIZE건만 반환하므로 오늘 데이터 있으면 이미 포함됨).
        """
        rows = seg_info.get("rows", [])
        seg_start = seg_info["seg_start"]
        seg_end = seg_info["seg_end"]

        # rows가 비어있으면 재조회
        if not rows:
            seg_data = await self._fetch_seg(seg_start, seg_end)
            if not seg_data:
                return 0
            rows = seg_data.get("rows", [])

        # 오늘/어제 필터
        target_rows = [r for r in rows if r.get("CHNG_DT", "") in (today, yesterday)]
        if not target_rows:
            return 0

        logger.info(
            f"[SmartSweep] 📥 {seg_start:,}~{seg_end:,}: "
            f"오늘/어제 {len(target_rows)}건 수집 시도"
        )

        # DB write — scraper 파이프라인 재사용
        try:
            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows(
                SVC_ID, target_rows, collected_by="smart_sweep"
            )
            return len(target_rows)
        except Exception as e:
            logger.warning(f"[SmartSweep] collect 실패 ({seg_start}~{seg_end}): {e}")
            return 0
