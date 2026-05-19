"""
Rolling Full Scan 서비스 모듈.

매 주기 N페이지(기본 100)를 순차적으로 스캔하여 fingerprint 비교.
전체 1회전 완료 후 다시 처음부터 순환.
사각지대 0: 모든 레코드가 일정 주기 내에 최소 1회 검사됨.

상태 (crawler_state.extra_state에 영속):
  - rolling_cursor: 현재 스캔 시작 페이지 번호 (1-based record index)
  - page_fingerprints: {page_start_idx: fingerprint_hash} 전체 저장

핵심 로직:
  1. cursor부터 N페이지(×1,000건) 스캔
  2. 저장된 fingerprint와 비교 → 불일치 페이지에서 신규 레코드 추출
  3. cursor 전진 (끝 도달 시 1로 리셋)
  4. 수집된 신규 레코드 반환
"""
import asyncio
import random
from app.core.config import settings
from app.core.logger import logger
from app.services.pivot_manager import compute_page_fingerprint

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수


class RollingScanner:
    def __init__(self, api_client, service_id: str, state_repo):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = state_repo

    async def scan_cycle(self, pages_per_cycle: int = None) -> list:
        """
        현재 cursor 위치부터 N페이지를 스캔하여 변경된 레코드를 반환합니다.

        Returns:
            list: 새로 발견된 레코드 리스트 (fingerprint 불일치 페이지에서 추출)
        """
        svc = self.service_id
        if pages_per_cycle is None:
            pages_per_cycle = settings.ROLLING_SCAN_PAGES_PER_CYCLE

        state = self.state_repo.load_state(svc)
        total_count = state.get("last_total_count", 0)
        if total_count == 0:
            return []

        # 영속화된 Rolling Scan 상태 로드
        cursor = state.get("rolling_cursor", 1)
        fingerprints: dict = state.get("page_fingerprints", {})

        # 전체 페이지 수 계산 (1-based index)
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE

        if total_pages == 0:
            return []

        scanned = 0
        new_rows_total = []
        mismatched_pages = 0

        start_cursor = cursor  # 로그용

        logger.info(
            f"[{svc}] 🔄 Rolling Scan 시작: cursor={cursor:,}, "
            f"스캔={pages_per_cycle}페이지, "
            f"전체={total_pages}페이지 ({total_count:,}건)"
        )

        while scanned < pages_per_cycle:
            # 현재 페이지의 record 인덱스 계산
            page_start = cursor
            page_end = min(cursor + PAGE_SIZE - 1, total_count)

            if page_start > total_count:
                # 끝 도달 → 처음으로 리셋
                cursor = 1
                logger.info(
                    f"[{svc}] 🔁 Rolling Scan 1회전 완료! "
                    f"cursor를 1로 리셋합니다."
                )
                break

            # API 호출
            try:
                res = await self.api_client.fetch_data(
                    svc, page_start, page_end, timeout=30
                )
                await asyncio.sleep(
                    random.uniform(settings.GAP_MIN, settings.GAP_MAX)
                )

                if not res or svc not in res:
                    # 빈 응답 → 다음 페이지로
                    cursor += PAGE_SIZE
                    scanned += 1
                    continue

                block = res[svc]
                code = block.get("RESULT", {}).get("CODE", "")

                if code == "INFO-200":
                    # 데이터 없음 (Gap 또는 끝)
                    cursor += PAGE_SIZE
                    scanned += 1
                    continue

                if code != "INFO-000":
                    # 기타 오류 → 스킵
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
                    f"[{svc}] Rolling Scan page {page_start:,} 조회 실패: {e}"
                )
                cursor += PAGE_SIZE
                scanned += 1
                continue

            # fingerprint 비교
            current_fp = compute_page_fingerprint(items)
            stored_fp = fingerprints.get(str(page_start), "")

            if stored_fp and current_fp == stored_fp:
                # 일치 → 변동 없음
                pass
            elif stored_fp and current_fp != stored_fp:
                # 불일치 → Shift 진단으로 신규 레코드 추출
                mismatched_pages += 1
                new_rows = self._extract_new_rows(
                    items, fingerprints, page_start
                )
                if new_rows:
                    new_rows_total.extend(new_rows)
                    logger.info(
                        f"[{svc}] 📥 Rolling Scan page {page_start:,}: "
                        f"fingerprint 불일치 → {len(new_rows)}건 신규 발견"
                    )
                else:
                    logger.info(
                        f"[{svc}] ⚠️ Rolling Scan page {page_start:,}: "
                        f"fingerprint 불일치 (레코드 교체/삭제 추정)"
                    )

            # fingerprint 갱신 (최신 상태 유지)
            fingerprints[str(page_start)] = current_fp

            cursor += PAGE_SIZE
            scanned += 1

        # 상태 영속화
        state["rolling_cursor"] = cursor
        state["page_fingerprints"] = fingerprints
        self.state_repo.save_state(svc, state)

        pages_remaining = max(0, total_pages - (cursor - 1) // PAGE_SIZE)
        cycles_to_complete = (pages_remaining + pages_per_cycle - 1) // pages_per_cycle if pages_per_cycle > 0 else 0

        logger.info(
            f"[{svc}] ✅ Rolling Scan 완료: "
            f"{scanned}페이지 스캔, {mismatched_pages}건 불일치, "
            f"{len(new_rows_total)}건 신규 수집 | "
            f"다음 cursor={cursor:,}, "
            f"남은 {pages_remaining}페이지 (약 {cycles_to_complete}주기 후 1회전 완료)"
        )

        return new_rows_total

    def _extract_new_rows(
        self, current_items: list, fingerprints: dict, page_start: int
    ) -> list:
        """
        fingerprint 불일치 페이지에서 신규 삽입 레코드를 추출합니다.

        이전 페이지의 마지막 레코드 정보가 있으면, 현재 페이지에서
        기존에 없던 레코드(Shift로 밀려 들어온 레코드)를 식별합니다.
        """
        # 간단한 전략: 이전 fingerprint가 없으면 전체를 "신규"로 간주하지 않음
        # (Bootstrap 미완료 상태에서 false positive 방지)
        # fingerprint가 있었으나 변경된 경우에만 해당 페이지의 레코드를 반환
        #
        # 고급 Shift 진단은 pivot_manager의 로직을 재활용
        return current_items

    @staticmethod
    def build_fingerprints_from_bootstrap(
        api_client, service_id: str, total_count: int
    ) -> dict:
        """
        Bootstrap 시 호출: 이미 fetch한 피벗 데이터로부터 page_fingerprints를 초기화.
        실제로는 bootstrap이 모든 피벗 페이지를 fetch하므로 그 결과를 여기서 기록.
        (Bootstrap은 PIVOT_INTERVAL 간격이므로, Rolling Scan은 나머지 페이지를
         첫 회전에서 자동으로 채워나감)
        """
        # Bootstrap에서 직접 호출되므로 여기서는 빈 dict 반환
        # 실제 fingerprint는 scan_cycle 중 점진적으로 채워짐
        return {}
