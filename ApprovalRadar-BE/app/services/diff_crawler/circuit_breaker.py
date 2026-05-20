import os
import json
from app.core.logger import logger

# [Phase 3] Circuit Breaker 임계값
CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv('CIRCUIT_BREAKER_THRESHOLD', '10000'))
# [B] Circuit Breaker 연속 발동 경고 임계값
CIRCUIT_BREAKER_ALERT_AFTER = 3

def check_circuit_breaker(svc: str, diff_count: int, state: dict, current_cb_count: int) -> tuple[bool, int]:
    """
    Circuit Breaker 발동 조건을 판단합니다.
    임계값 초과 시 경고 SSE를 발행하고, True와 갱신된 카운터를 반환합니다.
    """
    if diff_count <= CIRCUIT_BREAKER_THRESHOLD:
        return False, 0

    new_cb_count = current_cb_count + 1
    svc_name = {
        "I2859": "식품업소 인허가변경",
        "I2861": "음식점업소 인허가변경",
    }.get(svc, svc)

    logger.error(
        f"[{svc}] 🚨 [Circuit Breaker #{new_cb_count}] diff_count={diff_count:,}건이 "
        f"임계값({CIRCUIT_BREAKER_THRESHOLD:,})을 초과! "
        f"API 한도 초과 방지를 위해 이번 주기를 강제 중단합니다."
    )

    try:
        from app.core.events import broadcaster
        alert_msg = json.dumps({
            "type": "ALERT",
            "message": (
                f"[Circuit Breaker #{new_cb_count}] {svc_name} 변동분 {diff_count:,}건 감지 — "
                f"API 한도 초과 위험으로 이번 주기를 중단했습니다."
                + (f" ({CIRCUIT_BREAKER_ALERT_AFTER}회 연속 발동 시 강화 경고가 발송됩니다.)" if new_cb_count < CIRCUIT_BREAKER_ALERT_AFTER else "")
            )
        }, ensure_ascii=False)
        broadcaster.broadcast_sync(alert_msg)
    except Exception as e:
        logger.debug(f"SSE Alert 전송 실패 (무시): {e}")

    # [A-Tier Fix] CB 연속 발동 시 강화 경고
    if new_cb_count >= CIRCUIT_BREAKER_ALERT_AFTER:
        logger.critical(
            f"[{svc}] 🚨 [CB {new_cb_count}회 연속] "
            f"diff_count={diff_count:,}건 — 자동 복구 중단. "
            f"관리자 확인 필요: API 재정렬 가능성 또는 실제 대량 신규 등록."
        )
        try:
            from app.core.events import broadcaster
            alert_msg = json.dumps({
                "type": "ALERT",
                "message": (
                    f"[CB {new_cb_count}회 연속] {svc_name} {diff_count:,}건 감지 — "
                    f"자동 복구 중단됨. 관리자 확인 필요."
                )
            }, ensure_ascii=False)
            broadcaster.broadcast_sync(alert_msg)
        except Exception as e:
            logger.debug(f"SSE Alert 전송 실패 (무시): {e}")

    state["cb_consecutive_count"] = new_cb_count
    return True, new_cb_count
