"""
독립 Tail Ping 잡 — Rolling Scan과 분리된 경량 변동 감지.

매 N분(기본 5분) 간격으로 각 서비스의 Tail을 API 1회로 체크합니다.
변동 감지 시 즉시 scan_for_updates()를 트리거하여 Shift 분석 + 데이터 수집.

API 비용: 서비스당 1회/주기 (I2861 only → 일일 ~288회, 5,000 중 5.8%)

설계 원칙:
  - Rolling Scan과 완전 독립 (별도 스케줄러 잡)
  - 자체 ApiClient 인스턴스 사용 (세션 공유 X)
  - 변동 감지 시 trigger_immediate_scrape()로 스케줄러에 위임
  - Tail이 감소한 경우 (API 재정렬) 경고만 출력, 트리거 X
"""
import asyncio

from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.repositories.state_repository import StateRepository


# Tail Ping 주기 (분) — 스케줄러에서 참조
TAIL_PING_INTERVAL_MINUTES = 5


async def tail_ping_all_services():
    """
    모든 활성 서비스의 Tail을 1회 API로 체크하고,
    변동 감지 시 즉시 Scraper 잡을 트리거합니다.
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
                    # 부트스트랩 미완료 → 스킵
                    logger.debug(f"[Tail Ping] {svc_id} 부트스트랩 미완료 → 스킵")
                    continue

                if state.get("_bootstrapping"):
                    # 부트스트랩 진행 중 → 스킵
                    logger.debug(f"[Tail Ping] {svc_id} 부트스트랩 진행 중 → 스킵")
                    continue

                # ── total_count 1회 조회 (API 1회) ────────────────────
                res = await api_client.fetch_data(svc_id, 1, 1, timeout=10)
                if not res or svc_id not in res:
                    logger.debug(f"[Tail Ping] {svc_id} 응답 없음 → 스킵")
                    continue

                block = res[svc_id]
                code = block.get("RESULT", {}).get("CODE", "")
                if code not in ("INFO-000", "INFO-200"):
                    continue

                new_tail = int(block.get("total_count") or block.get("TOTAL_COUNT") or 0)

                if new_tail == known_tail:
                    logger.debug(
                        f"[Tail Ping] {svc_id} 변동 없음: {known_tail:,}건"
                    )
                    continue

                if new_tail > known_tail:
                    diff = new_tail - known_tail
                    svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(svc_id, svc_id)
                    logger.info(
                        f"🚨 [Tail Ping] {svc_name}({svc_id}) "
                        f"Tail 변동 감지! +{diff:,}건 "
                        f"({known_tail:,} → {new_tail:,}) "
                        f"→ 즉시 Scraper 트리거"
                    )
                    detected_any = True
                else:
                    # Tail 감소: API 재정렬 (야간 배치 등)
                    logger.warning(
                        f"[Tail Ping] {svc_id} Tail 감소 감지: "
                        f"{known_tail:,} → {new_tail:,} (API 재정렬 의심). "
                        f"다음 정기 크롤링에서 처리됩니다."
                    )

            except ApiKeysExhaustedError:
                logger.info("[Tail Ping] API 키 소진 → 중단")
                return
            except Exception as e:
                logger.warning(f"[Tail Ping] {svc_id} 오류: {e}")
                continue

    if detected_any:
        # 즉시 Scraper 트리거 (APScheduler 'date' 잡으로 등록)
        try:
            from app.core.scheduler import trigger_immediate_scrape
            trigger_immediate_scrape()
        except Exception as e:
            logger.error(f"[Tail Ping] Scraper 트리거 실패: {e}")


def run_tail_ping():
    """스케줄러 동기 래퍼: 별도 스레드에서 새 이벤트 루프를 생성하여 비동기 Tail Ping 실행."""
    asyncio.run(tail_ping_all_services())
