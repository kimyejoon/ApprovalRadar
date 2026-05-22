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

# 당일 단순 동기화로 확인된 업소 캐시 (재기동 시 초기화, 날짜 바뀌면 자동 리셋)
# DB 영속화로 부팅 시에도 유지됨
_sync_cache_date: str = ""
_sync_cache_lcns: set[str] = set()


def _load_sync_cache_from_db(target_date: str) -> set:
    """초기 폴링 시 DB에서 이미 검증된 단순동기화 업소를 로드."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT license_no FROM chng_dt_sync_verified WHERE target_date = ?",
                (target_date,)
            ).fetchall()
        return {r["license_no"] for r in rows}
    except Exception:
        return set()


def _save_sync_cache_to_db(target_date: str, lcns_list: list) -> None:
    """단순동기화 판명된 업소를 DB에 백업. 이미 있는 건 IGNORE."""
    if not lcns_list:
        return
    now = datetime.datetime.now().isoformat()
    try:
        with get_db() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO chng_dt_sync_verified "
                "(target_date, license_no, verified_at) VALUES (?, ?, ?)",
                [(target_date, lcns, now) for lcns in lcns_list]
            )
            conn.commit()
    except Exception as e:
        logger.debug(f"[CHNG_DT Poller] sync_verified DB 저장 실패: {e}")

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
        res = await api_client.fetch_data(service_i2861, 1, 10, LCNS_NO=lcns)
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
        "date": target_date, "pages": 0, "elapsed": 0.0,
        "api_raw_total_count": 0,  # I2500 API 응답의 실제 total_count
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
            MAX_CONSECUTIVE_EMPTY = 3  # 연속 빈 페이지 3개 → 중간 갭 허용 후 종료
            api_raw_total = 0  # 첫 페이지 응답의 total_count 필드

            logger.info(
                f"[전략C] 폴링 시작: CHNG_DT={target_date} | "
                f"최대 {MAX_PAGES}페이지/{MAX_PAGES * PAGE_SIZE:,}건 상한"
            )

            consecutive_empty = 0
            while page <= MAX_PAGES:
                start = (page - 1) * PAGE_SIZE + 1
                end = page * PAGE_SIZE
                page_fetch_start = time.time()

                page_res = await api_client.fetch_data(
                    SERVICE_ID, start, end, CHNG_DT=target_date
                )

                page_elapsed = round(time.time() - page_fetch_start, 1)

                if not page_res or SERVICE_ID not in page_res:
                    consecutive_empty += 1
                    logger.debug(
                        f"[전략C] P{page} 원시 응답 없음 → consecutive_empty={consecutive_empty}/{MAX_CONSECUTIVE_EMPTY}"
                    )
                    if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                        logger.info(f"[전략C] 연속 {MAX_CONSECUTIVE_EMPTY}페이지 빈 페이지 → 스캔 종료")
                        break
                    page += 1
                    continue

                svc_data = page_res[SERVICE_ID]
                rows = svc_data.get("row", [])

                # 첫 페이지에서 API total_count 캐치
                if page == 1:
                    raw_total_str = svc_data.get("total_count", "0")
                    try:
                        api_raw_total = int(raw_total_str)
                    except (ValueError, TypeError):
                        api_raw_total = 0
                    logger.info(
                        f"[전략C] I2500 API 엔드포인트 total_count={api_raw_total:,} "
                        f"(CHNG_DT={target_date})"
                    )

                if not rows:
                    consecutive_empty += 1
                    logger.debug(
                        f"[전략C] P{page} 행 0건 → consecutive_empty={consecutive_empty}/{MAX_CONSECUTIVE_EMPTY}"
                    )
                    if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                        logger.info(f"[전략C] 연속 {MAX_CONSECUTIVE_EMPTY}페이지 빈 페이지 → 스캔 종료")
                        break
                else:
                    consecutive_empty = 0  # 데이터 있으면 카운터 리셋
                    all_items.extend(rows)
                    logger.info(
                        f"[전략C] 폴링 P{page}/{MAX_PAGES} ✔ | "
                        f"이번 페이지 {len(rows):,}건 | "
                        f"누적 {len(all_items):,}건 | "
                        f"소요 {page_elapsed}초"
                    )

                page += 1

            result["api_raw_total_count"] = api_raw_total
            result["total"] = len(all_items)
            result["pages"] = page - 1

            logger.info(
                f"[전략C] I2500 전페이지 수집 완료: "
                f"API total={api_raw_total:,} | 실수집={len(all_items):,}건 | {page-1}페이지"
            )

            if not all_items:
                logger.debug(f"[CHNG_DT Poller] {target_date}: API 데이터 없음")
                result["elapsed"] = round(time.time() - start_time, 1)
                _save_poll_history(result)
                return result

            # 주: 단순 동기화 캐시 날짜 확인 / 다른 날짜면 리셋
            global _sync_cache_date, _sync_cache_lcns
            if _sync_cache_date != target_date:
                _sync_cache_date = target_date
                # DB에서 이미 검증된 단순동기화 로드 (재기동 후에도 유지)
                _sync_cache_lcns = _load_sync_cache_from_db(target_date)
                logger.debug(
                    f"[CHNG_DT Poller] 단순동기화 캐시 로드: {target_date} "
                    f"DB {len(_sync_cache_lcns):,}건"
                )

            # ── Step 2: 이미 오늘 변경건이 DB에 있는 LCNS 조회 (Batch SELECT) ──
            today_lcns_in_db: set[str] = set()
            lcns_list = [
                item["LCNS_NO"] for item in all_items if item.get("LCNS_NO")
            ]
            if lcns_list:
                CHUNK_SIZE = 900
                with get_db() as conn:
                    for i in range(0, len(lcns_list), CHUNK_SIZE):
                        batch = lcns_list[i : i + CHUNK_SIZE]
                        ph = ",".join(["?"] * len(batch))
                        rows_db = conn.execute(
                            f"SELECT license_no FROM businesses "
                            f"WHERE license_no IN ({ph}) AND last_event_date = ?",
                            batch + [target_date]
                        ).fetchall()
                        for row in rows_db:
                            today_lcns_in_db.add(row["license_no"])

            logger.info(
                f"[CHNG_DT Poller] DB 필터: "
                f"전체 {len(all_items):,}건 | 금일 이미수집 {len(today_lcns_in_db):,}건 | "
                f"단순동기화 캐시 {len(_sync_cache_lcns):,}건"
            )

            # ── Step 3: 후보군 필터링 ──
            #   제외 조건:
            #     (A) PRMS_DT == target_date → 신규등록 건 (변경이 아님)
            #     (B) 이미 DB에 last_event_date=target_date 레코드 존재 → 이미 수집됨
            #     (C) 동일 LCNS_NO 중복 (I2500 같은 페이지 내 중복)
            #     (D) 단순 동기화 캐시에 있는 업소 → 이미 당일 검증 완료, 변경없음 확인됨
            new_items = []
            seen_lcns_in_cycle: set[str] = set()
            skip_new_reg = 0
            skip_already_today = 0
            skip_dedup = 0
            skip_sync_cache = 0

            for item in all_items:
                lcns = item.get("LCNS_NO", "")
                if not lcns:
                    continue

                # (A) 신규등록 건 제외 (PRMS_DT == target_date)
                prms_dt = item.get("PRMS_DT") or ""
                if prms_dt == target_date:
                    skip_new_reg += 1
                    continue

                # (B) 이미 금일 변경건이 DB에 있는 경우 제외
                if lcns in today_lcns_in_db:
                    skip_already_today += 1
                    continue

                # (D) 단순 동기화 이미 확인됨 (in-memory 캐시) → 스킵
                #     첫 폴링에서 I2861 검증 후 단순동기화로 판명된 업소는
                #     이후 폴링에서 자동 스킵 (구소 폴링가속화)
                if lcns in _sync_cache_lcns:
                    skip_sync_cache += 1
                    continue

                # (C) 동일 폴링 사이클 내 중복 LCNS 제거 (I2861 검증은 1회로 충분)
                if lcns in seen_lcns_in_cycle:
                    skip_dedup += 1
                    continue
                seen_lcns_in_cycle.add(lcns)

                new_items.append(item)

            result["skipped"] = len(all_items) - len(new_items)

            logger.info(
                f"[CHNG_DT Poller] 필터 결과: "
                f"신규등록 스킵 {skip_new_reg:,}건 | "
                f"금일 이미수집 스킵 {skip_already_today:,}건 | "
                f"동기화캐시 스킵 {skip_sync_cache:,}건 | "
                f"중복 스킵 {skip_dedup:,}건 | "
                f"I2861 검증 대상 {len(new_items):,}건"
            )

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
            sync_lcns_this_round: list[str] = []
            for item, r_list in zip(new_items, task_results):
                mapped_rows.extend(r_list)
                # 단순 동기화 판명된 업소 → 캐시에 저장 (이후 폴링 스킵)
                if r_list and r_list[0].get("CHNG_PRVNS") in ("\uc2dc\uc2a4\ud15c\ub3d9\uae30\ud654(\uacfc\uac70\uc774\ub825)", "\ucd08\uae30\uc790\ub8cc\ub4f1\ub85d"):
                    lcns_key = item.get("LCNS_NO", "")
                    if lcns_key:
                        sync_lcns_this_round.append(lcns_key)

            if sync_lcns_this_round:
                _sync_cache_lcns.update(sync_lcns_this_round)
                # DB에도 영속저장 (재기동 후에도 스킵 보장)
                _save_sync_cache_to_db(target_date, sync_lcns_this_round)
                logger.info(
                    f"[CHNG_DT Poller] 폴링 캐시: 단순동기화 {len(sync_lcns_this_round):,}건 추가 → 누적 {len(_sync_cache_lcns):,}건 "
                    f"(다음 사이클에서 자동 스킵, DB 영속화 완료)"
                )

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
                    already_exists, pages_fetched, elapsed_sec, api_raw_total_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result["date"], now_iso,
                    result["total"], result["new"],
                    result["skipped"], result["pages"],
                    result["elapsed"],
                    result.get("api_raw_total_count", 0),
                )
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"[전략C] 이력 저장 실패: {e}")



async def _run_poller_async():
    """
    항상 어제 + 오늘 동시 폴링.

    근거:
    - I2500 CHNG_DT <= 로직 확인: 어제 날짜로 조회해도 오늘 레코드 포함 가능
    - 오늘 날짜 폴링이 업무시간 전이면 INFO-700 → 0건으로 무해하게 종료
    - 시간 제한 없이 24시간 최대 커버리지 확보
    """
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y%m%d")

    logger.info(
        f"[전략C] 🕐 어제({yesterday_str}) + 오늘({today_str}) 동시 폴링 시작"
    )

    # 어제 먼저 (자정 이후 즉시 포착)
    yesterday_result = await poll_changes_for_date(yesterday_str)
    # 오늘 (업무시간 전이면 0건, 업무시간 중이면 실시간 포착)
    today_result = await poll_changes_for_date(today_str)

    logger.info(
        f"[전략C] 📊 결과: "
        f"어제({yesterday_str}) API {yesterday_result['total']:,}건 → 신규 {yesterday_result['new']}건 | "
        f"오늘({today_str}) API {today_result['total']:,}건 → 신규 {today_result['new']}건"
    )



def run_chng_dt_poller():
    """스케줄러 동기 래퍼."""
    asyncio.run(_run_poller_async())
