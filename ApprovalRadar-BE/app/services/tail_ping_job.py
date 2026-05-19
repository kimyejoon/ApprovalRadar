"""
독립 Tail Ping 잡 — Ping-Only 경량 변동 감지.

매 N분(기본 5분) 간격으로 각 서비스의 known_tail+1 위치에
데이터가 존재하는지 API 1회로 직접 확인합니다.

★ total_count 의존 없음 — 직접 데이터 존재 여부를 확인하는 방식.
  _fetch_page(known_tail+1, known_tail+PAGE_SIZE) → 데이터 있으면 변동!

변동 감지 시 즉시 scan_for_updates()를 트리거하여
find_true_tail(이진탐색) + Shift 분석 + 데이터 수집을 scraper에 위임.

API 비용: 서비스당 1회/주기 (I2861 only → 일일 ~288회)
"""
import asyncio
import random

from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.repositories.state_repository import StateRepository

PAGE_SIZE = 1000  # diff_crawler.py와 동일
TAIL_PING_INTERVAL_MINUTES = 5


async def tail_ping_all_services():
    """
    모든 활성 서비스의 known_tail+1 위치에 데이터가 있는지 직접 확인.
    데이터 존재 시 → 즉시 Scraper 트리거 (find_true_tail + Shift는 scraper가 처리).
    """
    if ApiClient.is_exhausted():
        logger.debug("[Tail Ping] API 키 소진 상태 → 스킵")
        return

    if shutdown_event.is_set():
        return

    state_repo = StateRepository()
    service_ids = getattr(settings, "SERVICES", ["I2861"])
    detected_any = False

    async with ApiClient() as api_client:
        for svc_id in service_ids:
            if shutdown_event.is_set():
                break

            try:
                state = state_repo.load_state(svc_id)
                known_tail = state.get("last_total_count", 0)

                if known_tail == 0:
                    logger.debug(f"[Tail Ping] {svc_id} 부트스트랩 미완료 → 스킵")
                    continue

                if state.get("_bootstrapping"):
                    logger.debug(f"[Tail Ping] {svc_id} 부트스트랩 진행 중 → 스킵")
                    continue

                # ── Ping-Only: known_tail+1 위치에 데이터 존재 여부 직접 확인 ──
                # total_count 의존 없음 — 실제 데이터 존재 여부만 확인
                ping_start = known_tail + 1
                ping_end = known_tail + PAGE_SIZE
                res = await api_client.fetch_data(
                    svc_id, ping_start, ping_end, timeout=10
                )
                # WAF 방지 jitter
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

                if not res or svc_id not in res:
                    logger.info(f"[Tail Ping] {svc_id} 변동 없음 (known_tail={known_tail:,})")
                    continue

                block = res[svc_id]
                code = block.get("RESULT", {}).get("CODE", "")

                if code == "INFO-200":
                    # INFO-200 = 해당 범위에 데이터 없음 → 변동 없음
                    logger.info(f"[Tail Ping] {svc_id} 변동 없음 (known_tail={known_tail:,})")
                    continue

                if code != "INFO-000":
                    # 예상치 못한 응답 코드 → 스킵
                    logger.debug(
                        f"[Tail Ping] {svc_id} 예상외 응답: {code} → 스킵"
                    )
                    continue

                # INFO-000 = 데이터 존재! → known_tail 너머에 신규 데이터 있음
                rows = block.get("row", [])
                if rows:
                    svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(svc_id, svc_id)
                    logger.info(
                        f"🚨 [Tail Ping] {svc_name}({svc_id}) "
                        f"Tail 변동 감지! known_tail={known_tail:,} 이후 "
                        f"{len(rows)}건 데이터 존재 "
                        f"→ 즉시 Scraper 트리거"
                    )
                    detected_any = True
                else:
                    logger.info(f"[Tail Ping] {svc_id} 변동 없음 (known_tail={known_tail:,})")

            except ApiKeysExhaustedError:
                logger.info("[Tail Ping] API 키 소진 → 중단")
                return
            except Exception as e:
                logger.warning(f"[Tail Ping] {svc_id} 오류: {e}")
                continue

    if detected_any:
        try:
            from app.core.scheduler import trigger_immediate_scrape
            trigger_immediate_scrape()
        except Exception as e:
            logger.error(f"[Tail Ping] Scraper 트리거 실패: {e}")


def run_tail_ping():
    """스케줄러 동기 래퍼."""
    asyncio.run(tail_ping_all_services())
