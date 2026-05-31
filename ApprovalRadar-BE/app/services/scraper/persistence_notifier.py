import json
import asyncio
import threading
from app.core.logger import logger
from app.services.industry_filler import fill_industry_for_licenses

def trigger_sse_broadcast(count: int, service_id: str):
    """오늘 변동건 발생 시 SSE 즉시 발행"""
    try:
        from app.core.events import broadcaster
        update_data = json.dumps(
            {"type": "UPDATE", "count": count}, ensure_ascii=False
        )
        broadcaster.broadcast_sync(update_data)
        svc_name = {"I2859": "식품업소", "I2861": "음식점업소", "I2500": "신규등록"}.get(service_id, service_id)
        logger.info(
            f"🔔 [{svc_name}] 오늘 변동분 {count}건 감지 → SSE 발행!"
        )
    except Exception as e:
        logger.error(f"SSE 브로드캐스트 발행 실패: {e}")


def trigger_backfill_thread(lcns_list: list, service_id: str, thread_suffix: str):
    """백필 처리를 위한 백그라운드 데몬 스레드 구동"""
    logger.info(
        f"[Backfill] {len(lcns_list)}건 I2500 백필 → 백그라운드 시작 "
        f"(대표자+세부업종+연락처, SSE는 이미 발행 완료)"
    )
    threading.Thread(
        target=lambda lcns=lcns_list: asyncio.run(fill_industry_for_licenses(lcns)),
        daemon=True,
        name=f"BackfillThread-{thread_suffix}",
    ).start()
