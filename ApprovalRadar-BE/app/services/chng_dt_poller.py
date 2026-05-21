"""
I2500 CHNG_DT 폴러 — 3-Way 전략의 세 번째 축.

매 5분 간격으로 I2500 서비스에 CHNG_DT 파라미터를 넣어
변동 업소 목록을 직접 조회합니다.

시간대별 전략:
  - 00:00~18:59 → "어제" 날짜 폴링 (당일 데이터는 19:00 이후에야 반영)
  - 19:00~23:59 → "오늘" 날짜 폴링 (주 대상) + "어제" 보조 폴링

매 폴링 결과는 chng_dt_poll_history 테이블에 영속 저장되어
플레이그라운드에서 시간별 트렌드 차트를 그릴 수 있습니다.
"""
import asyncio
import datetime
import time

from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from database import get_db

# I2500 서비스 ID (인허가변동 이력 — CHNG_DT 필터 작동)
SERVICE_ID = "I2500"
PAGE_SIZE = 1000
POLL_INTERVAL_MINUTES = 5

# I2500 → businesses 테이블 필드 매핑
FIELD_MAP = {
    "LCNS_NO": "license_no",
    "BSSH_NM": "business_name",
    "ADDR": "address",
    "PRSDNT_NM": "representative_name",
    "TELNO": "phone_number",
    "INDUTY_CD_NM": "industry_type",
    "PRMS_DT": "license_date",
}


async def _verify_actual_change(api_client: ApiClient, lcns: str, target_date: str, item_i2500: dict) -> list[dict]:
    """
    I2861 단건 조회를 날려 진짜 변경 정보와 허수를 구분합니다.
    """
    service_i2861 = "I2861"
    try:
        res = await api_client.fetch_data(service_i2861, 1, 10, LCNS_NO=lcns, timeout=15)
    except Exception as e:
        logger.warning(f"[CHNG_DT Poller] I2861 검증 API 호출 실패 (LCNS_NO={lcns}): {e}")
        # API 호출 실패 시에는 안전을 위해 I2500 정보 그대로 오늘 자 변동으로 처리
        return [{
            "LCNS_NO": lcns,
            "BSSH_NM": item_i2500.get("BSSH_NM", ""),
            "SITE_ADDR": item_i2500.get("ADDR", ""),
            "PRSDNT_NM": item_i2500.get("PRSDNT_NM", ""),
            "BSN_STATE_NM": None,
            "PRMS_DT": item_i2500.get("PRMS_DT", ""),
            "TELNO": item_i2500.get("TELNO", ""),
            "INDUTY_CD_NM": item_i2500.get("INDUTY_CD_NM", ""),
            "CHNG_DT": target_date,
            "SITE_ADDR_RDN": item_i2500.get("ADDR", ""),
        }]
        
    rows = []
    if res and service_i2861 in res:
        rows = res[service_i2861].get("row", [])
        
    # 오늘 자 변경행이 있는지 필터링
    today_rows = [r for r in rows if r.get("CHNG_DT") == target_date]
    
    if today_rows:
        logger.info(f"[CHNG_DT Poller] 🟢 {lcns} ({item_i2500.get('BSSH_NM', '')}) 진짜 오늘 변경 검증 성공 (사유: {today_rows[0].get('CHNG_PRVNS')})")
        mapped = []
        for r in today_rows:
            mapped.append({
                "LCNS_NO": lcns,
                "BSSH_NM": r.get("BSSH_NM") or item_i2500.get("BSSH_NM"),
                "SITE_ADDR": r.get("SITE_ADDR") or item_i2500.get("ADDR"),
                "PRSDNT_NM": r.get("PRSDNT_NM") or item_i2500.get("PRSDNT_NM"),
                "BSN_STATE_NM": None,
                "PRMS_DT": item_i2500.get("PRMS_DT"),
                "TELNO": r.get("TELNO") or item_i2500.get("TELNO"),
                "INDUTY_CD_NM": r.get("INDUTY_CD_NM") or item_i2500.get("INDUTY_CD_NM"),
                "CHNG_DT": target_date,
                "SITE_ADDR_RDN": r.get("SITE_ADDR") or item_i2500.get("ADDR"),
                "CHNG_PRVNS": r.get("CHNG_PRVNS"),
                "CHNG_BF_CN": r.get("CHNG_BF_CN"),
                "CHNG_AF_CN": r.get("CHNG_AF_CN"),
            })
        return mapped
    else:
        # 허수 (단순 DB 싱크만 오늘 됨)
        actual_date = None
        if rows:
            dates = [r.get("CHNG_DT") for r in rows if r.get("CHNG_DT")]
            if dates:
                actual_date = max(dates)
                
        if not actual_date:
            # 변경 이력이 아예 없는 신규 업소인 경우 인허가일자 사용
            actual_date = item_i2500.get("PRMS_DT")
            
        if not actual_date:
            actual_date = "19700101"
            
        logger.info(f"[CHNG_DT Poller] ⚪ {lcns} ({item_i2500.get('BSSH_NM', '')}) 단순 동기화 건 감지 (실제최종일자: {actual_date})")
        return [{
            "LCNS_NO": lcns,
            "BSSH_NM": item_i2500.get("BSSH_NM"),
            "SITE_ADDR": item_i2500.get("ADDR"),
            "PRSDNT_NM": item_i2500.get("PRSDNT_NM"),
            "BSN_STATE_NM": None,
            "PRMS_DT": item_i2500.get("PRMS_DT"),
            "TELNO": item_i2500.get("TELNO"),
            "INDUTY_CD_NM": item_i2500.get("INDUTY_CD_NM"),
            "CHNG_DT": actual_date, # 과거 날짜로 설정하여 DB에는 기록되나 오늘 자 실시간 알림에서 제외
            "SITE_ADDR_RDN": item_i2500.get("ADDR"),
            "CHNG_PRVNS": "초기자료등록" if not rows else "시스템동기화(과거이력)",
            "CHNG_BF_CN": None,
            "CHNG_AF_CN": None,
        }]


async def poll_changes_for_date(target_date: str) -> dict:
    """
    I2500 CHNG_DT=target_date 조회 → DB에 없는 건만 INSERT.

    Args:
        target_date: 조회할 날짜 (YYYYMMDD).

    Returns:
        dict: {"total": API 전체, "new": 신규 INSERT, "skipped": 중복 스킵,
               "date": 대상날짜, "pages": 페이지수, "elapsed": 소요시간}
    """
    start_time = time.time()
    result = {
        "total": 0, "new": 0, "skipped": 0,
        "date": target_date, "pages": 0, "elapsed": 0.0
    }

    if ApiClient.is_exhausted():
        logger.debug(f"[CHNG_DT Poller] API 키 소진 → {target_date} 스킵")
        return result

    if shutdown_event.is_set():
        return result

    try:
        async with ApiClient() as api_client:
            # ── Step 1: 전체 페이지 순회 (빈 페이지까지 반복) ──
            all_items = []
            page = 1
            MAX_PAGES = 20  # 안전장치 (20,000건 상한)

            while page <= MAX_PAGES:
                start = (page - 1) * PAGE_SIZE + 1
                end = page * PAGE_SIZE

                page_res = await api_client.fetch_data(
                    SERVICE_ID, start, end, CHNG_DT=target_date, timeout=15
                )

                if not page_res or SERVICE_ID not in page_res:
                    break

                rows = page_res[SERVICE_ID].get("row", [])
                if not rows:
                    break

                all_items.extend(rows)
                page += 1

            result["total"] = len(all_items)
            result["pages"] = page - 1

            if not all_items:
                logger.debug(f"[CHNG_DT Poller] {target_date}: API 데이터 없음")
                result["elapsed"] = round(time.time() - start_time, 1)
                _save_poll_history(result)
                return result

            # ── Step 2: DB 중복 조회 최적화 (Batch SELECT) ──
            existing_pairs = set()
            lcns_list = [
                item["LCNS_NO"] for item in all_items if item.get("LCNS_NO")
            ]
            if lcns_list:
                # 900개씩 chunking (SQLite 파라미터 개수 제한 999개 대비)
                CHUNK_SIZE = 900
                with get_db() as conn:
                    for i in range(0, len(lcns_list), CHUNK_SIZE):
                        batch = lcns_list[i : i + CHUNK_SIZE]
                        ph = ",".join(["?"] * len(batch))
                        rows = conn.execute(
                            f"SELECT license_no, last_event_date FROM businesses "
                            f"WHERE license_no IN ({ph})",
                            batch
                        ).fetchall()
                        for row in rows:
                            existing_pairs.add((row["license_no"], row["last_event_date"]))

            # ── Step 3: 오늘 이미 검사 완료된 건 및 기존 수집된 건 필터 ──
            date_hyphen = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
            processed_lcns_today = set()
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT license_no FROM businesses WHERE updated_at LIKE ? OR created_at LIKE ?",
                    (f"{date_hyphen}%", f"{date_hyphen}%")
                ).fetchall()
                processed_lcns_today = {r["license_no"] for r in rows}

            new_items = []
            for item in all_items:
                lcns = item.get("LCNS_NO", "")
                if not lcns:
                    continue
                if lcns in processed_lcns_today:
                    continue
                pair = (lcns, target_date)
                if pair not in existing_pairs:
                    new_items.append(item)
                    existing_pairs.add(pair)

            result["skipped"] = len(all_items) - len(new_items)

            if not new_items:
                logger.info(
                    f"[CHNG_DT Poller] {target_date}: {len(all_items):,}건 전부 기존 수집됨 "
                    f"→ Rolling Scan 정상 커버 중 ✅"
                )
                result["elapsed"] = round(time.time() - start_time, 1)
                _save_poll_history(result)
                return result

            # ── Step 4: I2500 후보군 검증 및 I2861 형식 변환 ──
            logger.info(f"[CHNG_DT Poller] 🔍 신규 후보군 {len(new_items):,}건에 대해 I2861 변경이력 교차 검증 시작 (동시성 10)...")
            semaphore = asyncio.Semaphore(10)
            
            async def verify_task(item):
                async with semaphore:
                    lcns = item.get("LCNS_NO", "")
                    return await _verify_actual_change(api_client, lcns, target_date, item)
            
            tasks = [verify_task(item) for item in new_items]
            task_results = await asyncio.gather(*tasks)
            
            mapped_rows = []
            for r_list in task_results:
                mapped_rows.extend(r_list)

            logger.info(
                f"[CHNG_DT Poller] 🆕 {target_date}: "
                f"신규 {len(new_items):,}/{len(all_items):,}건 → scraper 파이프라인"
            )

            from scraper import run_scraper_for_service_with_rows
            await run_scraper_for_service_with_rows("I2861", mapped_rows, collected_by="chng_dt_poller")
            result["new"] = len(new_items)

            elapsed = round(time.time() - start_time, 1)
            result["elapsed"] = elapsed

            logger.info(
                f"🔔 [CHNG_DT Poller] 완료: CHNG_DT={target_date} "
                f"API {len(all_items):,}건 → 신규 {len(new_items):,}건 INSERT, "
                f"기존 {result['skipped']:,}건 ({elapsed}초, {page}p)"
            )

    except ApiKeysExhaustedError:
        logger.info("[CHNG_DT Poller] API 키 소진 → 다음 주기에 재시도")
    except Exception as e:
        logger.error(f"[CHNG_DT Poller] 오류: {e}", exc_info=True)

    result["elapsed"] = round(time.time() - start_time, 1)
    _save_poll_history(result)
    return result


def _save_poll_history(result: dict):
    """폴링 결과를 DB에 영속 저장."""
    try:
        now_iso = datetime.datetime.now().isoformat()
        with get_db() as conn:
            conn.execute(
                """INSERT INTO chng_dt_poll_history
                   (poll_date, polled_at, total_api_count, new_inserted,
                    already_exists, pages_fetched, elapsed_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    result["date"], now_iso,
                    result["total"], result["new"],
                    result["skipped"], result["pages"],
                    result["elapsed"]
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"[CHNG_DT Poller] 이력 저장 실패: {e}")


async def _run_poller_async():
    """
    시간대별 폴링 전략:
    - 00:00~18:59 → 어제 날짜만 폴링
    - 19:00~23:59 → 오늘 폴링 (주) + 어제 보조 폴링
    """
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")
    hour = now.hour

    if hour >= 19:
        # 19:00 이후: 오늘 (주) + 어제 (보조)
        logger.info(
            f"[전략C] 🕐 {hour}시 → 오늘({today_str}) 주 폴링 + 어제({yesterday_str}) 보조"
        )
        today_result = await poll_changes_for_date(today_str)
        yesterday_result = await poll_changes_for_date(yesterday_str)

        logger.info(
            f"[전략C] 📊 결과: 오늘({today_str}) API {today_result['total']:,}건 "
            f"→ 신규 {today_result['new']}건 | "
            f"어제({yesterday_str}) API {yesterday_result['total']:,}건 "
            f"→ 신규 {yesterday_result['new']}건"
        )
    else:
        # 00:00~18:59: 어제만
        logger.info(
            f"[전략C] 🕐 {hour}시 → 어제({yesterday_str}) 폴링 (당일 데이터 19시 이후 반영)"
        )
        yesterday_result = await poll_changes_for_date(yesterday_str)

        logger.info(
            f"[전략C] 📊 결과: 어제({yesterday_str}) API {yesterday_result['total']:,}건 "
            f"→ 신규 {yesterday_result['new']}건 / 기존 {yesterday_result['skipped']:,}건 "
            f"({yesterday_result['elapsed']}초)"
        )


def run_chng_dt_poller():
    """스케줄러 동기 래퍼."""
    asyncio.run(_run_poller_async())
