"""
Rolling Full Scan 서비스 모듈 (듀얼 커서 버전).

매 주기 N페이지(기본 100)를 2개 커서(A/B)로 나눠 순차 스캔.
- cursor_a: 전체 데이터의 전반부 (0 ~ mid)
- cursor_b: 전체 데이터의 후반부 (mid ~ end)
각 커서가 자기 영역을 순환하므로, 1커서 대비 회전 시간 2배 단축.

상태 (crawler_state.extra_state에 영속):
  - rolling_cursor_a: 전반부 스캔 위치
  - rolling_cursor_b: 후반부 스캔 위치
  - page_fingerprints: {page_start_idx: fingerprint_hash}

핵심 로직:
  1. cursor_a에서 N/2페이지, cursor_b에서 N/2페이지 스캔
  2. 저장된 fingerprint와 비교 → 불일치 시 신규 레코드 추출
  3. 각 커서 전진 (영역 끝 도달 시 영역 시작으로 리셋)
  4. 수집된 신규 레코드 반환
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

    async def scan_cycle(self, pages_per_cycle: int = None, flush_callback=None) -> list:
        """
        듀얼 커서로 전반부/후반부를 동시에 스캔하여 변경된 레코드를 반환합니다.

        Args:
            pages_per_cycle: 주기당 스캔 페이지 수
            flush_callback: async callable(rows) — 커서별 스캔 완료 시 즉시 호출.
                           DB INSERT + SSE 발행을 위해 사용.
                           호출되면 해당 rows는 반환 리스트에서 제외됨.

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

        # 듀얼 커서 로드
        cursor_a = state.get("rolling_cursor_a", 1)
        cursor_b = state.get("rolling_cursor_b", mid_record)
        fingerprints: dict = state.get("page_fingerprints", {})

        # 각 커서에 절반씩 할당
        pages_a = pages_per_cycle // 2
        pages_b = pages_per_cycle - pages_a  # 홀수일 경우 B가 1개 더

        # 영역 범위
        range_a = (1, mid_record - 1)           # 전반부
        range_b = (mid_record, total_count)     # 후반부

        pages_a_total = (range_a[1]) // PAGE_SIZE if range_a[1] > 0 else 0
        pages_b_total = ((range_b[1] - range_b[0] + 1) + PAGE_SIZE - 1) // PAGE_SIZE if range_b[1] >= range_b[0] else 0

        logger.info(
            f"[{svc}] 🔄 Rolling Scan 시작 (듀얼 커서): "
            f"A={cursor_a:,}~{range_a[1]:,} ({pages_a}p), "
            f"B={cursor_b:,}~{range_b[1]:,} ({pages_b}p) | "
            f"전체={total_pages}페이지 ({total_count:,}건)"
        )

        new_rows_total = []
        mismatched_pages = 0
        total_scanned = 0

        # ── 커서 A 스캔 (전반부) ──
        scanned_a, new_a, mismatch_a, cursor_a = await self._scan_range(
            svc, cursor_a, range_a[0], range_a[1],
            pages_a, fingerprints, "A"
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
            pages_b, fingerprints, "B"
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

        # 상태 영속화
        state["rolling_cursor_a"] = cursor_a
        state["rolling_cursor_b"] = cursor_b
        state["page_fingerprints"] = fingerprints
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
                        (len(new_b) if new_b and flush_callback else 0)

        logger.info(
            f"[{svc}] ✅ Rolling Scan 완료: "
            f"{total_scanned}페이지 스캔 (A:{scanned_a}+B:{scanned_b}), "
            f"{mismatched_pages}건 불일치, "
            f"{flushed_total + len(new_rows_total)}건 신규 수집 | "
            f"다음 A={cursor_a:,}, B={cursor_b:,} | "
            f"약 {cycles_to_complete}주기 후 1회전 완료"
        )

        return new_rows_total

    async def _scan_range(
        self, svc: str, cursor: int,
        range_start: int, range_end: int,
        max_pages: int, fingerprints: dict,
        label: str
    ) -> tuple:
        """
        지정된 범위 내에서 cursor부터 max_pages만큼 스캔합니다.

        Returns:
            (scanned_count, new_rows, mismatch_count, new_cursor)
        """
        scanned = 0
        new_rows = []
        mismatched = 0
        new_fp_count = 0  # 신규 fingerprint 저장 수
        match_count = 0   # fingerprint 일치 수
        today_found = 0   # 오늘 CHNG_DT 신규 발견 수
        today_str = datetime.now().strftime("%Y%m%d")

        logger.info(
            f"[{svc}] 📡 커서 {label} 스캔 시작: "
            f"범위 {cursor:,}~{range_end:,}, 최대 {max_pages}페이지 (오늘={today_str})"
        )

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

            # ── [관찰 모드] 오늘 CHNG_DT 존재 여부만 로깅 ──────────────
            # 주력 탐지: Tail Ping + Shift/Pivot, fingerprint 불일치
            # today_filter는 전략C(19:00)에서 교차검증
            today_count_in_page = sum(
                1 for item in items
                if item.get("CHNG_DT", "") == today_str
            )
            if today_count_in_page:
                today_found += today_count_in_page
                logger.debug(
                    f"[{svc}] 📊 커서 {label} page {page_start:,}: "
                    f"오늘({today_str}) {today_count_in_page}건 존재 "
                    f"(관찰 모드, 수집은 Tail Ping/전략C에서)"
                )

            # ── fingerprint 비교 ──────────────────────────────────
            current_fp = compute_page_fingerprint(items)
            stored_fp = fingerprints.get(str(page_start), "")

            if not stored_fp:
                # 첫 스캔: fingerprint 신규 저장
                new_fp_count += 1
            elif current_fp == stored_fp:
                # 일치: 변동 없음
                match_count += 1
            else:
                # 불일치: 변동 감지! (오늘 외 레코드도 포함)
                mismatched += 1
                extracted = self._extract_new_rows(items, fingerprints, page_start)
                if extracted:
                    # 오늘 CHNG_DT 레코드는 이미 위에서 추가됨 → 오늘 외 레코드만 추가
                    non_today = [
                        r for r in extracted
                        if r.get("CHNG_DT", "") != today_str
                    ]
                    if non_today:
                        new_rows.extend(non_today)
                    logger.info(
                        f"[{svc}] 📥 커서 {label} page {page_start:,}: "
                        f"fingerprint 불일치 → {len(extracted)}건 신규 발견"
                    )
                else:
                    logger.warning(
                        f"[{svc}] ⚠️ 커서 {label} page {page_start:,}: "
                        f"fingerprint 불일치 (레코드 교체/삭제 추정)"
                    )

            # fingerprint 갱신
            fingerprints[str(page_start)] = current_fp
            cursor += PAGE_SIZE
            scanned += 1

            # 매 10페이지마다 진행률 로그
            if scanned % 10 == 0:
                logger.info(
                    f"[{svc}] 📊 커서 {label} 진행: {scanned}/{max_pages}p "
                    f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
                    f"오늘:{today_found}) 현재 page={page_start:,}"
                )

        # 커서별 완료 요약
        if today_found > 0:
            logger.info(
                f"[{svc}] 🆕 커서 {label}: 오늘({today_str}) 변동분 {today_found}건 즉시 감지!"
            )
        logger.info(
            f"[{svc}] ✅ 커서 {label} 완료: {scanned}p 스캔 "
            f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
            f"오늘:{today_found}) → {len(new_rows)}건 수집"
        )

        return scanned, new_rows, mismatched, cursor

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
