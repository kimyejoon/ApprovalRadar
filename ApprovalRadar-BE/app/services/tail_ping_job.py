"""
독립 Tail Ping + Multi-Point Sentinel 잡.

매 N분(기본 5분) 간격으로 두 가지 방법으로 변동을 감지합니다:

1. [Tail Ping] known_tail+1 위치에 데이터가 존재하는지 직접 확인 (API 1회)
   → 모든 삽입은 Tail을 증가시키므로 가장 확실한 감지

2. [Multi-Point Sentinel] 저장된 피벗 fingerprint 중 3~5개를 랜덤 샘플링하여
   현재 API 데이터와 비교 (API 3~5회)
   → 삽입 위치 이후의 모든 피벗이 shift되므로 중간 삽입도 감지

변동 감지 시 즉시 scan_for_updates()를 트리거하여
find_true_tail(이진탐색) + Shift 분석 + 데이터 수집을 scraper에 위임.

API 비용: 서비스당 4~6회/주기 (I2861 only → 일일 ~1,200~1,700회, 예산 24~34%)

★ total_count 의존 없음 — 모든 판단은 실제 데이터 존재/fingerprint 비교로 수행.
"""
import asyncio
import random

from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.repositories.state_repository import StateRepository
from app.services.pivot_manager import compute_page_fingerprint

PAGE_SIZE = 1000
TAIL_PING_INTERVAL_MINUTES = 5

# Multi-Point Sentinel: 주기당 랜덤 샘플링할 피벗 수
SENTINEL_SAMPLES = 3


async def tail_ping_all_services():
    """
    모든 활성 서비스에 대해:
    1. Tail Ping (known_tail+1 데이터 존재 확인)
    2. Multi-Point Sentinel (랜덤 피벗 fingerprint 비교)
    둘 중 하나라도 변동 감지 시 → 즉시 Scraper 트리거.
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

                tail_detected = False
                sentinel_detected = False

                # ── 0. 역방향 검증: known_tail 근방에 데이터 존재하는지 확인 ──
                # ⚠️ API는 Gappy 인덱스: 단일 위치에 데이터 없을 수 있음 (Gap)
                # → 단일 위치 대신 known_tail 포함 범위(PAGE_SIZE)로 조회하여 Gap 오탐 방지
                range_start = max(1, known_tail - PAGE_SIZE + 1)
                tail_valid_res = await api_client.fetch_data(
                    svc_id, range_start, known_tail, timeout=10
                )
                await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

                tail_is_valid = False
                if tail_valid_res and svc_id in tail_valid_res:
                    vblock = tail_valid_res[svc_id]
                    vcode = vblock.get("RESULT", {}).get("CODE", "")
                    if vcode == "INFO-000" and vblock.get("row"):
                        tail_is_valid = True

                if not tail_is_valid:
                    # known_tail 근방 전체에 데이터 없음 → 진짜 축소/재정렬!
                    svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(svc_id, svc_id)
                    logger.warning(
                        f"🚨 [Tail Ping] {svc_name}({svc_id}) "
                        f"known_tail={known_tail:,} 근방 [{range_start:,}~{known_tail:,}] "
                        f"범위에 데이터 없음! 실제 축소/재정렬 감지 → Scraper 트리거"
                    )
                    tail_detected = True
                else:
                    # ── 1. Tail Ping: known_tail+1 데이터 존재 확인 ────────
                    ping_start = known_tail + 1
                    ping_end = known_tail + PAGE_SIZE
                    res = await api_client.fetch_data(
                        svc_id, ping_start, ping_end, timeout=10
                    )
                    await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

                    if res and svc_id in res:
                        block = res[svc_id]
                        code = block.get("RESULT", {}).get("CODE", "")
                        if code == "INFO-000" and block.get("row"):
                            rows = block["row"]
                            svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(svc_id, svc_id)
                            logger.info(
                                f"🚨 [Tail Ping] {svc_name}({svc_id}) "
                                f"Tail 변동 감지! known_tail={known_tail:,} 이후 "
                                f"{len(rows)}건 존재 → Scraper 트리거"
                            )
                            tail_detected = True
                        elif code == "INFO-200":
                            logger.info(
                                f"[Tail Ping] {svc_id} Tail 변동 없음 "
                                f"(known_tail={known_tail:,})"
                            )
                        # 기타 코드 → 무시
                    else:
                        logger.debug(f"[Tail Ping] {svc_id} Tail Ping 응답 없음")

                # ── 2. Multi-Point Sentinel: 랜덤 피벗 fingerprint 비교 ──
                if not tail_detected:
                    sentinel_detected = await _check_sentinels(
                        api_client, svc_id, state
                    )

                if tail_detected or sentinel_detected:
                    detected_any = True

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


async def _check_sentinels(
    api_client, svc_id: str, state: dict
) -> bool:
    """
    저장된 피벗 중 랜덤 N개의 fingerprint를 현재 API 데이터와 비교.
    하나라도 불일치하면 중간 삽입(Shift) 발생으로 판단.

    원리: 인덱스 X에 삽입 → X 이후 모든 레코드가 1칸 밀림
    → X 이후에 위치한 피벗의 fingerprint가 변함
    → 랜덤 3~5개 중 하나라도 잡힘
    """
    pivots = state.get("pivots", {})
    if not pivots:
        return False

    # fingerprint가 있는 피벗만 대상
    fp_pivots = [
        (idx_str, pdata) for idx_str, pdata in pivots.items()
        if isinstance(pdata, dict) and pdata.get("fingerprint")
    ]

    if not fp_pivots:
        return False

    # 랜덤 샘플링
    sample_size = min(SENTINEL_SAMPLES, len(fp_pivots))
    sampled = random.sample(fp_pivots, sample_size)

    for idx_str, pdata in sampled:
        if shutdown_event.is_set():
            break

        idx = int(idx_str)
        stored_fp = pdata["fingerprint"]

        try:
            res = await api_client.fetch_data(
                svc_id, idx, idx + PAGE_SIZE - 1, timeout=10
            )
            await asyncio.sleep(random.uniform(settings.GAP_MIN, settings.GAP_MAX))

            if not res or svc_id not in res:
                continue

            block = res[svc_id]
            code = block.get("RESULT", {}).get("CODE", "")
            if code != "INFO-000":
                continue

            rows = block.get("row", [])
            if not rows:
                continue

            current_fp = compute_page_fingerprint(rows)

            if current_fp != stored_fp:
                svc_name = {"I2859": "식품업소", "I2861": "음식점업소"}.get(svc_id, svc_id)
                logger.info(
                    f"🚨 [Sentinel] {svc_name}({svc_id}) "
                    f"피벗 {idx:,} fingerprint 불일치 감지! "
                    f"(중간 삽입/Shift 발생) → Scraper 트리거"
                )
                return True
            else:
                logger.debug(
                    f"[Sentinel] {svc_id} 피벗 {idx:,} fingerprint 일치"
                )

        except ApiKeysExhaustedError:
            raise
        except Exception as e:
            logger.debug(f"[Sentinel] {svc_id} 피벗 {idx:,} 조회 실패: {e}")
            continue

    logger.debug(
        f"[Sentinel] {svc_id} {sample_size}개 피벗 모두 일치 → 변동 없음"
    )
    return False


def run_tail_ping():
    """스케줄러 동기 래퍼."""
    asyncio.run(tail_ping_all_services())
