import asyncio
import random
import sqlite3
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event
from app.services.pivot_manager import compute_page_fingerprint
from app.services.crawler_constants import PAGE_SIZE
from database import get_db, DB_FILE

class RollingScanOps:
    def __init__(self, api_client, service_id: str):
        self.api_client = api_client
        self.service_id = service_id

    async def scan_single_page(
        self, svc: str, page_start: int, total_count: int,
        fingerprints: dict, scan_times: dict
    ) -> tuple:
        """
        단일 페이지 스캔 + fingerprint 비교.
        Returns: (scanned_count, new_rows, mismatch_count)
        """
        if shutdown_event.is_set():
            return (0, [], 0)

        page_end = min(page_start + PAGE_SIZE - 1, total_count)
        fp_key = str(page_start)

        try:
            data = await self.api_client.fetch_data(
                self.service_id, page_start, page_end
            )
        except Exception as e:
            logger.debug(f"[{svc}] 페이지 {page_start} API 실패: {e}")
            return (0, [], 0)

        if not data or self.service_id not in data:
            return (1, [], 0)

        rows = data[self.service_id].get("row", [])
        if not rows:
            return (1, [], 0)

        # Fingerprint 비교
        new_fp = compute_page_fingerprint(rows)
        old_fp = fingerprints.get(fp_key)
        fingerprints[fp_key] = new_fp
        scan_times[fp_key] = datetime.now().isoformat()

        mismatch = 0
        new_rows = []

        if old_fp and old_fp != new_fp:
            mismatch = 1
            # 불일치 → DB에 없는 레코드 찾기
            today_str = datetime.now().strftime("%Y%m%d")
            yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

            lcns_list = [r.get("LCNS_NO", "") for r in rows if r.get("LCNS_NO")]
            existing_set = set()
            if lcns_list:
                with get_db() as conn:
                    ph = ",".join(["?"] * len(lcns_list))
                    db_rows = conn.execute(
                        f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({ph})",
                        lcns_list
                    ).fetchall()
                    for r in db_rows:
                        existing_set.add((r["license_no"], r["last_event_date"]))

            for row in rows:
                lcns = row.get("LCNS_NO", "")
                chng_dt = row.get("CHNG_DT", "")
                if lcns and chng_dt in (today_str, yesterday_str):
                    if (lcns, chng_dt) not in existing_set:
                        new_rows.append(row)

        return (1, new_rows, mismatch)

    async def scan_range(
        self, svc: str, cursor: int,
        range_start: int, range_end: int,
        max_pages: int, fingerprints: dict, scan_times: dict,
        label: str
    ) -> tuple:
        """
        지정된 범위 내에서 cursor부터 max_pages만큼 스캔합니다.
        [최적화] DB에 없는 레코드를 batch로 감지하여 즉시 수집.

        Returns:
            (scanned_count, new_rows, mismatch_count, new_cursor)
        """
        scanned = 0
        new_rows = []
        mismatched = 0
        new_fp_count = 0  # 신규 fingerprint 저장 수
        match_count = 0   # fingerprint 일치 수
        today_found = 0   # 오늘 CHNG_DT 신규 발견 수
        yesterday_found = 0  # 어제 CHNG_DT 신규 발견 수
        db_miss_count = 0  # DB 미존재 레코드 수
        today_str = datetime.now().strftime("%Y%m%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        # ── 인사이트 통계 수집용 ──
        all_chng_dts = []   # 전체 CHNG_DT 수집 (분포 분석)
        lcns_sort_asc = 0   # LCNS_NO 오름차순 페이지 수
        lcns_sort_desc = 0  # LCNS_NO 내림차순 페이지 수
        lcns_no_sort = 0    # 정렬 불명 페이지 수

        # DB batch 조회용 — 스레드 로컬 캐싱 커넥션 (close하지 않음)
        db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        db_conn.row_factory = sqlite3.Row

        logger.info(
            f"[{svc}] 📡 커서 {label} 스캔 시작: "
            f"범위 {cursor:,}~{range_end:,}, 최대 {max_pages}페이지 (오늘={today_str})"
        )

        try:
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

                # ── DB 미존재 이벤트 batch 감지 ──────────────────
                lcns_list = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]
                if lcns_list:
                    # batch 조회: DB에 이미 있는 (license_no, last_event_date) 쌍
                    placeholders = ",".join(["?"] * len(lcns_list))
                    existing_cursor = db_conn.execute(
                        f"SELECT license_no, last_event_date FROM businesses WHERE license_no IN ({placeholders})",
                        lcns_list
                    )
                    existing_pairs = {(row[0], row[1]) for row in existing_cursor.fetchall()}

                    # DB에 (LCNS, CHNG_DT) 쌍이 없는 레코드 = 신규 이력 → 수집
                    missing_items = [
                        item for item in items
                        if item.get("LCNS_NO", "")
                        and (item["LCNS_NO"], item.get("CHNG_DT", "")) not in existing_pairs
                    ]
                    if missing_items:
                        db_miss_count += len(missing_items)
                        new_rows.extend(missing_items)

                        today_in_missing = sum(
                            1 for item in missing_items
                            if item.get("CHNG_DT", "") == today_str
                        )
                        yesterday_in_missing = sum(
                            1 for item in missing_items
                            if item.get("CHNG_DT", "") == yesterday_str
                        )
                        if today_in_missing:
                            today_found += today_in_missing
                        if yesterday_in_missing:
                            yesterday_found += yesterday_in_missing
                            logger.info(
                                f"[{svc}] 🆕 커서 {label} page {page_start:,}: "
                                f"오늘({today_str}) 변동분 {today_in_missing}건 즉시 감지!"
                            )

                        if len(missing_items) >= 5:
                            logger.info(
                                f"[{svc}] 📥 커서 {label} page {page_start:,}: "
                                f"DB 미존재 {len(missing_items)}건 발견 → 수집 대상 추가"
                            )

                # ── fingerprint 비교 ──────────────────────────────────
                current_fp = compute_page_fingerprint(items)
                stored_fp = fingerprints.get(str(page_start), "")

                # 스캔 시각 기록
                scan_times[str(page_start)] = datetime.now().isoformat()

                if not stored_fp:
                    # 첫 스캔: fingerprint 신규 저장
                    new_fp_count += 1
                elif current_fp == stored_fp:
                    # 일치: 변동 없음
                    match_count += 1
                else:
                    # 불일치: 변동 감지!
                    mismatched += 1
                    # DB miss 체크에서 이미 수집했으므로 중복 추가 방지
                    logger.debug(
                        f"[{svc}] 커서 {label} page {page_start:,}: "
                        f"fingerprint 불일치 (DB miss 체크에서 이미 처리)"
                    )

                # ── [인사이트] 페이지별 CHNG_DT/LCNS_NO 통계 ──────────────
                page_chng_dts = [item.get("CHNG_DT", "") for item in items if item.get("CHNG_DT")]
                all_chng_dts.extend(page_chng_dts)

                # LCNS_NO 정렬 패턴 분석
                lcns_nos = [item.get("LCNS_NO", "") for item in items if item.get("LCNS_NO")]
                if len(lcns_nos) >= 2:
                    is_asc = all(lcns_nos[i] <= lcns_nos[i+1] for i in range(min(10, len(lcns_nos)-1)))
                    is_desc = all(lcns_nos[i] >= lcns_nos[i+1] for i in range(min(10, len(lcns_nos)-1)))
                    if is_asc:
                        lcns_sort_asc += 1
                    elif is_desc:
                        lcns_sort_desc += 1
                    else:
                        lcns_no_sort += 1

                # fingerprint 갱신
                fingerprints[str(page_start)] = current_fp
                cursor += PAGE_SIZE
                scanned += 1

                # 매 10페이지마다 진행률 + 인사이트 로그
                if scanned % 10 == 0:
                    # CHNG_DT 분포 분석
                    insight = ""
                    if all_chng_dts:
                        sorted_dts = sorted(all_chng_dts)
                        oldest = sorted_dts[0]
                        newest = sorted_dts[-1]
                        # 연도별 분포 요약
                        year_dist = {}
                        for dt in all_chng_dts:
                            yr = dt[:4] if len(dt) >= 4 else "????"
                            year_dist[yr] = year_dist.get(yr, 0) + 1
                        top_years = sorted(year_dist.items(), key=lambda x: -x[1])[:3]
                        yr_summary = " ".join(f"{y}:{c}" for y, c in top_years)
                        sort_pattern = (
                            f"LCNS정렬:↑{lcns_sort_asc}/↓{lcns_sort_desc}/∅{lcns_no_sort}"
                        )
                        insight = f" | DT범위:{oldest}~{newest} 연도분포:[{yr_summary}] {sort_pattern}"

                    logger.info(
                        f"[{svc}] 📊 커서 {label} 진행: {scanned}/{max_pages}p "
                        f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
                        f"DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found}){insight}"
                    )

        finally:
            try:
                db_conn.close()
            except Exception:
                pass

        # 커서별 완료 요약
        if today_found > 0:
            logger.info(
                f"[{svc}] 🆕 커서 {label}: 오늘({today_str}) 변동분 {today_found}건 즉시 감지!"
            )
        if yesterday_found > 0:
            logger.info(
                f"[{svc}] 📋 커서 {label}: 어제({yesterday_str}) 변동분 {yesterday_found}건 감지"
            )
        logger.info(
            f"[{svc}] ✅ 커서 {label} 완료: {scanned}p 스캔 "
            f"(일치:{match_count} 신규FP:{new_fp_count} 불일치:{mismatched} "
            f"DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found}) → {len(new_rows)}건 수집"
        )

        return scanned, new_rows, mismatched, cursor

    async def scan_random_probe(
        self, svc: str, max_pages: int, total_count: int,
        cursor_a: int, cursor_b: int,
        range_a: tuple, range_b: tuple,
        scan_times: dict | None = None
    ) -> tuple:
        """
        Track 2: 전체 범위에서 랜덤 페이지를 샘플링하여 DB 미존재 레코드를 수집합니다.
        Sequential 커서가 현재 스캔 중인 근방은 제외하여 중복을 방지합니다.

        Returns:
            (scanned_count, new_rows)
        """
        today_str = datetime.now().strftime("%Y%m%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE

        # Sequential 커서 근방 제외 (±30p 범위)
        exclude_margin = 30 * PAGE_SIZE
        exclude_a = set(range(
            max(1, cursor_a - exclude_margin),
            min(total_count, cursor_a + exclude_margin) + 1,
            PAGE_SIZE
        ))
        exclude_b = set(range(
            max(1, cursor_b - exclude_margin),
            min(total_count, cursor_b + exclude_margin) + 1,
            PAGE_SIZE
        ))
        excluded = exclude_a | exclude_b

        # 전체 가능 페이지 시작 위치 생성
        all_page_starts = [
            p * PAGE_SIZE + 1 for p in range(total_pages)
            if (p * PAGE_SIZE + 1) not in excluded
        ]

        if not all_page_starts:
            return 0, []

        # 랜덤 샘플링
        sample_size = min(max_pages, len(all_page_starts))
        sampled_starts = sorted(random.sample(all_page_starts, sample_size))

        logger.info(
            f"[{svc}] 🎲 Random Probe 시작: {sample_size}p "
            f"(전체 {len(all_page_starts)}p 중 랜덤 샘플링, 오늘={today_str})"
        )

        scanned = 0
        new_rows = []
        today_found = 0
        yesterday_found = 0
        db_miss_count = 0

        # DB batch 조회용 커넥션
        db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        db_conn.row_factory = sqlite3.Row

        try:
            for page_start in sampled_starts:
                page_end = min(page_start + PAGE_SIZE - 1, total_count)

                try:
                    res = await self.api_client.fetch_data(
                        svc, page_start, page_end, timeout=15
                    )
                except Exception:
                    continue

                if not res or svc not in res:
                    continue

                block = res[svc]
                code = block.get("RESULT", {}).get("CODE", "")
                if code != "INFO-000":
                    continue

                items = block.get("row", [])
                if not items:
                    continue

                scanned += 1

                # 스캔 시각 기록
                if scan_times is not None:
                    scan_times[str(page_start)] = datetime.now().isoformat()

                # DB batch miss 체크
                lcns_list = []
                for item in items:
                    ln = item.get("LCNS_NO", "")
                    if ln:
                        lcns_list.append(ln)

                if lcns_list:
                    unique_lcns = list(set(lcns_list))
                    placeholders = ",".join(["?"] * len(unique_lcns))
                    existing = set()
                    cursor = db_conn.execute(
                        f"SELECT license_no FROM businesses WHERE license_no IN ({placeholders})",
                        unique_lcns
                    )
                    for row in cursor.fetchall():
                        existing.add(row["license_no"])

                    page_new = [item for item in items if item.get("LCNS_NO", "") and item.get("LCNS_NO") not in existing]
                    if page_new:
                        db_miss_count += len(page_new)
                        new_rows.extend(page_new)

                # 오늘/어제 CHNG_DT 체크
                page_today = sum(1 for item in items if item.get("CHNG_DT", "").startswith(today_str))
                page_yesterday = sum(1 for item in items if item.get("CHNG_DT", "").startswith(yesterday_str))
                if page_today > 0:
                    today_found += page_today
                    logger.info(
                        f"[{svc}] 🎯 오늘 데이터 발견! page {page_start:,}: "
                        f"{page_today}건 (CHNG_DT={today_str})"
                    )
                if page_yesterday > 0:
                    yesterday_found += page_yesterday

                # 10p마다 진행 로그
                if scanned % 10 == 0:
                    logger.info(
                        f"[{svc}] 📊 Random Probe 진행: {scanned}/{sample_size}p "
                        f"(DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found})"
                    )

                await asyncio.sleep(0.3)

        finally:
            try:
                db_conn.close()
            except Exception:
                pass

        logger.info(
            f"[{svc}] ✅ Random Probe 완료: {scanned}p → "
            f"{len(new_rows)}건 수집 (DB미존재:{db_miss_count} 오늘:{today_found} 어제:{yesterday_found})"
        )

        return scanned, new_rows
