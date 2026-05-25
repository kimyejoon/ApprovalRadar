"""
I2500 CHNG_DT 폴러 — 3-Way 전략의 세 번째 축.

매 5분 간격으로 I2500 서비스에 CHNG_DT 파라미터를 넣어
변동 업소 목록을 직접 조회합니다.

앵커 전략 (3중 폴링):
  D-3 → D-2 → D-1 순서로 순차 폴링
  - D-3: 가장 넓은 범위, 캐시/DB 먼저 채우기
  - D-2: D-3 이후 추가된 레코드
  - D-1: D-2/D-3에서 누락된 ~15건 포속
         (LCNS가 CHNG_DT 업데이트로 다른 날짜로 이동한 케이스)

  중복 처리: INSERT OR IGNORE + sync_cache 자동 처리
  근거: test_anchor.py 실증 — D-1 ⊄ D-2 ≒ 15건 누락 확인

매 폴링 결과는 chng_dt_poll_history 테이블에 영속 저장되어
플레이그라운드에서 시간별 트렌드 차트를 그릴 수 있습니다.
"""
import asyncio
import datetime
import time

from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients.foodsafety_api import ApiClient, ApiKeysExhaustedError
from app.clients.worker_pool import ApiWorkerPool
from database import get_db
from app.core.industries import FOOD_SERVICE_INDUSTRIES

# I2500 서비스 ID (인허가변동 이력 — CHNG_DT 필터 작동)
SERVICE_ID = "I2500"
PAGE_SIZE = 1000
POLL_INTERVAL_MINUTES = 5

# 단순 동기화로 확인된 업소 캐시 (재기동 시 초기화, DB 영속화로 부팅 시에도 유지됨)
_sync_cache_loaded: bool = False
_sync_cache_lcns: dict[str, str] = {}  # license_no -> max_verified_target_date


def _load_sync_cache_from_db() -> dict[str, str]:
    """초기 폴링 시 DB에서 이미 검증된 단순동기화 업소와 그 시점의 target_date를 로드."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT license_no, MAX(target_date) as max_date FROM chng_dt_sync_verified GROUP BY license_no"
            ).fetchall()
        return {r["license_no"]: r["max_date"] for r in rows}
    except Exception:
        return {}


def _save_sync_cache_to_db(lcns_to_chng_dt: list[tuple[str, str]]) -> None:
    """단순동기화 판명된 업소를 DB에 백업. 이미 있는 건 IGNORE."""
    if not lcns_to_chng_dt:
        return
    now = datetime.datetime.now().isoformat()
    try:
        with get_db() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO chng_dt_sync_verified "
                "(target_date, license_no, verified_at) VALUES (?, ?, ?)",
                [(chng_dt, lcns, now) for lcns, chng_dt in lcns_to_chng_dt]
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


async def _verify_actual_change(
    api_client: ApiClient, lcns: str, target_date: str, item_i2500: dict,
    prog: str = ""
) -> list[dict]:
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

    # ── 최근 5일 이내 변경건 감지 (앵커가 2일 전이어도 오늘 변경 포착) ──
    # I2500 CHNG_DT는 >= 필터이므로 앵커 날짜에 오늘 실제 변경건이 포함됨
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y%m%d")
    recent_rows = [r for r in rows if (r.get("CHNG_DT") or "") >= cutoff_date]

    if recent_rows:
        _mk = api_client.key_manager._mask_key(
            api_client.key_manager.api_keys[api_client.key_manager.current_key_idx]
        )
        logger.info(
            f"[CHNG_DT Poller | {_mk}] {prog} 🟢 {lcns} ({item_i2500.get('BSSH_NM', '')}) "
            f"최근 변경 {len(recent_rows)}건 감지 "
            f"(최신: {max(r.get('CHNG_DT','') for r in recent_rows)}, 사유: {recent_rows[0].get('CHNG_PRVNS')})"
        )
        mapped = []
        for r in recent_rows:
            mapped.append({
                "LCNS_NO": lcns,
                "BSSH_NM": r.get("BSSH_NM") or item_i2500.get("BSSH_NM"),
                "SITE_ADDR": r.get("SITE_ADDR") or item_i2500.get("ADDR"),
                "PRSDNT_NM": r.get("PRSDNT_NM") or item_i2500.get("PRSDNT_NM"),
                "BSN_STATE_NM": None,
                "PRMS_DT": item_i2500.get("PRMS_DT"),
                "TELNO": r.get("TELNO") or item_i2500.get("TELNO"),
                "INDUTY_CD_NM": r.get("INDUTY_CD_NM") or item_i2500.get("INDUTY_CD_NM"),
                "CHNG_DT": r.get("CHNG_DT"),  # I2861 실제 날짜 그대로
                "SITE_ADDR_RDN": r.get("SITE_ADDR") or item_i2500.get("ADDR"),
                "CHNG_PRVNS": r.get("CHNG_PRVNS"),
                "CHNG_BF_CN": r.get("CHNG_BF_CN"),
                "CHNG_AF_CN": r.get("CHNG_AF_CN"),
            })
        return mapped
    else:
        _mk = api_client.key_manager._mask_key(
            api_client.key_manager.api_keys[api_client.key_manager.current_key_idx]
        )
        if rows:
            # ⚪ I2861 이력 있으나 최근 5일 밖 → 실제 검증된 변경이므로 DB 저장
            # (INSERT OR IGNORE로 중복 방지, SSE는 발행 안 함)
            actual_date = max((r.get("CHNG_DT") or "") for r in rows)
            logger.info(
                f"[CHNG_DT Poller | {_mk}] {prog} ⚪ {lcns} ({item_i2500.get('BSSH_NM', '')}) "
                f"과거 변경 이력 감지 (최신: {actual_date}) — 과거 날짜로 DB 저장"
            )
            mapped = []
            for r in rows:
                mapped.append({
                    "LCNS_NO": lcns,
                    "BSSH_NM": r.get("BSSH_NM") or item_i2500.get("BSSH_NM"),
                    "SITE_ADDR": r.get("SITE_ADDR") or item_i2500.get("ADDR"),
                    "PRSDNT_NM": r.get("PRSDNT_NM") or item_i2500.get("PRSDNT_NM"),
                    "BSN_STATE_NM": None,
                    "PRMS_DT": item_i2500.get("PRMS_DT"),
                    "TELNO": r.get("TELNO") or item_i2500.get("TELNO"),
                    "INDUTY_CD_NM": r.get("INDUTY_CD_NM") or item_i2500.get("INDUTY_CD_NM"),
                    "CHNG_DT": r.get("CHNG_DT"),  # I2861 실제 날짜 그대로
                    "SITE_ADDR_RDN": r.get("SITE_ADDR") or item_i2500.get("ADDR"),
                    "CHNG_PRVNS": r.get("CHNG_PRVNS") or "시스템동기화(과거이력)",
                    "CHNG_BF_CN": r.get("CHNG_BF_CN"),
                    "CHNG_AF_CN": r.get("CHNG_AF_CN"),
                })
            return mapped
        else:
            # ⚫ 진짜 허수: I2861 이력이 아예 없음 → DB 저장 불가, 캐시만 등록
            logger.info(
                f"[CHNG_DT Poller | {_mk}] {prog} ⚫ {lcns} ({item_i2500.get('BSSH_NM', '')}) "
                f"I2861 이력 없음 (신규등록 전 DB 동기화) — DB 저장 제외"
            )
            return [{"LCNS_NO": lcns, "CHNG_DT": None, "CHNG_PRVNS": "초기자료등록"}]



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
        result["elapsed"] = round(time.time() - start_time, 1)
        _save_poll_history(result)
        return result

    if shutdown_event.is_set():
        result["elapsed"] = round(time.time() - start_time, 1)
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
                    _mk = api_client.key_manager._mask_key(
                        api_client.key_manager.api_keys[api_client.key_manager.current_key_idx]
                    )
                    logger.info(
                        f"[전략C | {_mk}] 폴링 P{page}/{MAX_PAGES} ✔ | "
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
            global _sync_cache_loaded, _sync_cache_lcns
            if not _sync_cache_loaded:
                _sync_cache_lcns = _load_sync_cache_from_db()
                _sync_cache_loaded = True
                logger.debug(
                    f"[CHNG_DT Poller] 단순동기화 캐시 로드: DB {len(_sync_cache_lcns):,}건"
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

                # (A-2) 식품위생법 적용 업종만 수집 (비식품 업종 완전 차단)
                # FOOD_SERVICE_INDUSTRIES = 일반음식점·휴게음식점·제과점영업·위탁급식영업·집단급식소·유흥주점영업·단란주점
                induty = (item.get("INDUTY_CD_NM") or "").strip()
                if induty and induty not in FOOD_SERVICE_INDUSTRIES:
                    skip_new_reg += 1   # 스킵 카운터 공유 (업종 외)
                    continue

                # (B) 이미 금일 변경건이 DB에 있는 경우 제외
                if lcns in today_lcns_in_db:
                    skip_already_today += 1
                    continue

                # (D) 단순 동기화 이미 확인됨 (in-memory 캐시) → 스킵
                #     첫 폴링에서 I2861 검증 후 단순동기화로 판명된 업소는
                #     이후 폴링에서 자동 스킵 (구소 폴링가속화)
                chng_dt = item.get("CHNG_DT") or ""
                cached_max_date = _sync_cache_lcns.get(lcns)
                if cached_max_date and cached_max_date >= chng_dt:
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

            # ── Step 4: I2500 후보군 검증 및 즉시/배치 삽입 ─────────────────────────
            # 오늘 날짜 진짜 변경건 → 검증 완료 즉시 DB 삽입 + SSE 1건 발행
            # 과거 날짜 / 단순동기화 건 → pending_past_rows 배치 큐 → 전건 완료 후 일괄 삽입
            pool        = ApiWorkerPool(10, label="CHNG_DT Poller")
            eff_workers = pool.n_workers
            logger.info(
                f"[CHNG_DT Poller] 🔍 신규 후보군 {len(new_items):,}건에 대해 "
                f"I2861 변경이력 교차 검증 시작 "
                f"(검증 워커: {eff_workers}개, 살아있는 키: {pool.n_alive}개)..."
            )
            semaphore = pool.semaphore
            from scraper import run_scraper_for_service_with_rows

            total_items   = len(new_items)
            today_str_poll = datetime.datetime.now().strftime("%Y%m%d")
            pending_past_rows: list[dict] = []   # 과거 날짜 데이터 배치 큐
            sync_lcns_this_round: list[tuple[str, str]] = []
            real_today_count: int = 0            # 즉시 삽입된 오늘 변경건 수
            done_count: int = 0                  # 검증 완료 건수 (진행률용)

            async def verify_and_insert_task(item, worker_idx: int):
                nonlocal real_today_count, done_count
                async with semaphore:
                    lcns = item.get("LCNS_NO", "")
                    verify_client = pool.get_client(worker_idx)
                    done_count += 1
                    prog = f"[{done_count}/{total_items}]"
                    r_list = await _verify_actual_change(verify_client, lcns, target_date, item, prog=prog)

                    if not r_list:
                        return

                    # 진짜 허수 판별: I2861 이력이 아예 없는 경우만 (초기자료등록)
                    # ⚪ 과거 이력(시스템동기화) 은 DB 저장 대상이므로 is_sync=False
                    is_sync = r_list[0].get("CHNG_PRVNS") == "초기자료등록"

                    # 오늘/과거 날짜 분리 (CHNG_DT=None인 허수 마커 제외)
                    today_rows = [r for r in r_list if r.get("CHNG_DT") == today_str_poll]
                    past_rows  = [r for r in r_list if r.get("CHNG_DT") and r.get("CHNG_DT") != today_str_poll]

                    # ── 오늘 날짜 진짜 변경건: 즉시 삽입 + 즉시 SSE ─────────────────
                    if today_rows:
                        await run_scraper_for_service_with_rows(
                            "I2861", today_rows, collected_by="chng_dt_poller"
                        )
                        real_today_count += len(today_rows)
                        prvns = today_rows[0].get("CHNG_PRVNS") or "인허가변동"
                        bf_cn = today_rows[0].get("CHNG_BF_CN") or ""
                        af_cn = today_rows[0].get("CHNG_AF_CN") or ""
                        detail = f" ({bf_cn} → {af_cn})" if (bf_cn or af_cn) else ""
                        logger.info(
                            f"[CHNG_DT Poller] {prog} 🟢 즉시 삽입+SSE: {lcns} "
                            f"({item.get('BSSH_NM', '')}) [{prvns}]{detail}"
                        )
                        # 즉시 삽입 후 today_lcns_in_db 갱신 → I2861 스캔과의 중복 방지
                        today_lcns_in_db.add(lcns)

                    # ── 과거 날짜 데이터: 배치 큐에 적립 ─────────────────────────────
                    # I2861 검증된 실제 이력은 CHNG_DT가 있으므로 항상 저장
                    # CHNG_DT=None 허수 마커는 위에서 이미 제외됨
                    if past_rows:
                        pending_past_rows.extend(past_rows)

                    # 검증 완료 캐시에 추가하여 다음 폴링 시 중복 조회 방지 (변동건, 과거건, 허수 전체 포함)
                    chng_dt = item.get("CHNG_DT") or target_date
                    sync_lcns_this_round.append((lcns, chng_dt))

            await asyncio.gather(*[verify_and_insert_task(item, i % eff_workers) for i, item in enumerate(new_items)])

            # ── 단순동기화 캐시 업데이트 ────────────────────────────────────────
            if sync_lcns_this_round:
                for lcns, chng_dt in sync_lcns_this_round:
                    _sync_cache_lcns[lcns] = max(_sync_cache_lcns.get(lcns, ""), chng_dt)
                _save_sync_cache_to_db(sync_lcns_this_round)
                logger.info(
                    f"[CHNG_DT Poller] 폴링 캐시: 단순동기화 {len(sync_lcns_this_round):,}건 추가 → "
                    f"누적 {len(_sync_cache_lcns):,}건 (다음 사이클에서 자동 스킵, DB 영속화 완료)"
                )

            # ── 과거 날짜 데이터 배치 삽입 ────────────────────────────────────
            if pending_past_rows:
                logger.info(
                    f"[CHNG_DT Poller] 📦 과거 날짜 데이터 {len(pending_past_rows):,}건 배치 삽입"
                )
                await run_scraper_for_service_with_rows(
                    "I2861", pending_past_rows, collected_by="chng_dt_poller"
                )

            result["new"] = len(new_items)
            elapsed = round(time.time() - start_time, 1)
            result["elapsed"] = elapsed

            logger.info(
                f"🔔 [CHNG_DT Poller] 완료: CHNG_DT={target_date} "
                f"API {len(all_items):,}건 → 신규 {len(new_items):,}건 처리 "
                f"(오늘 즉시삽입 {real_today_count}건 / 과거배치 {len(pending_past_rows):,}건), "
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
    I2500 CHNG_DT 3중 폴링 (D-3 → D-2 → D-1).

    앵커 전략:
    - D-3부터 폴링하여 캐시/DB를 먼저 채움
    - D-2, D-1은 실질적 신규만 처리 (INSERT OR IGNORE 로 중복 안전)
    - D-1에만 D-2/D-3에 없는 ~15건 노못 (test_anchor 실증)

    근거: D-1 ⊄ D-2 ≒ 15건 누락 (LCNS_NO가 CHNG_DT 업데이트되어 다른 날짜로 이동)
    """
    now = datetime.datetime.now()

    # D-3 → D-2 → D-1 순서 (넓은 범위부터 먼저 수집)
    anchors = [
        ((now - datetime.timedelta(days=3)).strftime("%Y%m%d"), "D-3"),
        ((now - datetime.timedelta(days=2)).strftime("%Y%m%d"), "D-2"),
        ((now - datetime.timedelta(days=1)).strftime("%Y%m%d"), "D-1"),
    ]

    logger.info(
        f"[전략C] 3중 폴링 시작 — "
        f"{anchors[0][0]}(D-3) / {anchors[1][0]}(D-2) / {anchors[2][0]}(D-1)"
    )

    total_new = 0
    for anchor_date, label in anchors:
        if shutdown_event.is_set():
            logger.info("[CHNG_DT Poller] shutdown 감지 → 중단")
            break

        result = await poll_changes_for_date(anchor_date)
        total_new += result["new"]

        logger.info(
            f"[전략C] 3중 {label}({anchor_date}): "
            f"API {result['total']:,}건 → 신규 {result['new']}건 "
            f"(스킵 {result['skipped']:,}건 | {result['elapsed']:.1f}s)"
        )

    logger.info(f"[전략C] 🔔 3중 폴링 완료: 총 신규 {total_new}건")


def run_chng_dt_poller():
    """스케줄러 동기 래퍼."""
    asyncio.run(_run_poller_async())
