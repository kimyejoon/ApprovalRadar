import asyncio
import threading
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event

PAGE_SIZE = 1000
BOOTSTRAP_SEMAPHORE_LIMIT = 3
_GLOBAL_BOOTSTRAP_SEMAPHORE = threading.Semaphore(1)

# total_count 필드가 신뢰 가능한 서비스 목록
RELIABLE_TOTAL_COUNT_SERVICES: set[str] = set()

async def run_bootstrap_standalone(engine) -> None:
    """
    Bootstrap 전용 독립 ApiClient 사용.
    GLOBAL_BOOTSTRAP_SEMAPHORE로 직렬화하여 동시 실행을 차단하고 WAF 회피.
    """
    svc = engine.service_id
    logger.info(f"[{svc}] 🔄 Bootstrap 스레드 시작 — 전역 Bootstrap Semaphore 대기 중...")
    acquired = _GLOBAL_BOOTSTRAP_SEMAPHORE.acquire(timeout=3600)  # 최대 1시간 대기
    if not acquired:
        logger.error(
            f"[{svc}] ❌ Bootstrap Semaphore 대기 시간 초과 (1시간). "
            f"_bootstrapping 플래그 해제 후 다음 주기에 재시도."
        )
        try:
            state = engine.state_repo.load_state(svc)
            state.pop("_bootstrapping", None)
            engine.state_repo.save_state(svc, state)
        except Exception:
            pass
        return

    logger.info(f"[{svc}] 🔄 Bootstrap 스레드 시작 (독립 ApiClient 사용, 직렬화 진행 중)")
    from app.clients.foodsafety_api import ApiClient as _ApiClient
    try:
        async with _ApiClient() as fresh_client:
            original_client = engine.api_client
            engine.api_client = fresh_client
            try:
                await bootstrap(engine)
            except Exception as e:
                logger.error(
                    f"[{svc}] ❌ Bootstrap 스레드 오류: {e}",
                    exc_info=True
                )
                try:
                    state = engine.state_repo.load_state(svc)
                    state.pop("_bootstrapping", None)
                    engine.state_repo.save_state(svc, state)
                    logger.warning(
                        f"[{svc}] ⚠️ Bootstrap 실패 — _bootstrapping 플래그 해제. "
                        f"다음 주기에 재시도합니다."
                    )
                except Exception as cleanup_err:
                    logger.error(f"[{svc}] 플래그 해제 실패: {cleanup_err}")
            finally:
                engine.api_client = original_client
    finally:
        _GLOBAL_BOOTSTRAP_SEMAPHORE.release()
        logger.info(f"[{svc}] 🔓 Bootstrap Semaphore 해제 — 다음 서비스 Bootstrap 가능")


async def find_true_tail(engine, known_tail: int = 0) -> int:
    """실제 데이터 끝(Tail) 위치를 정확하게 탐색합니다."""
    svc = engine.service_id

    # ── 전략 A: total_count 신뢰 서비스 ──────────────────────────────────────
    if svc in RELIABLE_TOTAL_COUNT_SERVICES:
        logger.info(f"[{svc}][전략A] total_count 직접 조회 (Ping 스킵)")
        res = await engine.api_client.fetch_data(svc, 1, 1, timeout=10)
        if res and svc in res:
            block = res[svc]
            if block.get("RESULT", {}).get("CODE") in ("INFO-000", "INFO-200"):
                total_count = int(block.get("total_count") or block.get("TOTAL_COUNT") or 0)
                if total_count > 0:
                    if known_tail > 0 and total_count < known_tail * 0.5:
                        logger.warning(
                            f"[{svc}][전략A] ⚠️ total_count={total_count:,}이 "
                            f"known_tail={known_tail:,}의 50% 미만 — API 오응답 의심. "
                            f"전략B(이진탐색)로 자동 전환합니다."
                        )
                    elif known_tail > 0 and total_count == known_tail:
                        logger.debug(f"[{svc}][전략A] 변동 없음: total_count={total_count:,} == known_tail={known_tail:,}")
                        logger.info(
                            f"[{svc}] ✔️ Tail 조사 완료: 현재 전체 {total_count:,}건 — 이번 주기 신규 인허가변동 없음."
                        )
                        return total_count
                    elif total_count > known_tail:
                        logger.info(
                            f"[{svc}] 🚨 Tail 조사 결과: 전체 {total_count:,}건 감지 → 이전({known_tail:,})보다 "
                            f"+{total_count - known_tail:,}건 신규 인허가변동 가능성 포착!"
                        )
                        return total_count
                    else:
                        logger.info(f"[{svc}][전략A] Tail 확정: {total_count:,}건 (total_count 직접)")
                        return total_count
        logger.warning(f"[{svc}][전략A] total_count 읽기 실패 또는 오응답, 페이지 탐색(전략B)으로 폴백")

    # ── 전략 B: 지수점프 + 이진탐색 + Gap허용 스캔 ───────────────────────
    logger.info(f"[{svc}][Bootstrapper] Tail 탐색 시작 (known_tail={known_tail:,})")

    if known_tail > 0:
        range_start = max(1, known_tail - PAGE_SIZE + 1)
        tail_check = await engine._fetch_page(range_start, known_tail)
        if not tail_check:
            logger.warning(
                f"[{svc}] ⚠️ known_tail={known_tail:,} 근방 [{range_start:,}~{known_tail:,}] "
                f"범위에 데이터 없음! API 재정렬/축소 감지. 이진탐색으로 실제 tail 재탐색..."
            )
            engine._reshuffled = True
            known_tail = 0
        else:
            ping = await engine._fetch_page(known_tail + 1, known_tail + PAGE_SIZE)
            if not ping:
                logger.info(
                    f"[{svc}] ✔️ Tail 조사 완료: 현재 전체 {known_tail:,}건 — "
                    f"{known_tail+1:,}번 이후 데이터 없음 → 이번 주기 신규 발생 없음."
                )
                return known_tail
            logger.info(
                f"[{svc}] 📌 Ping: {known_tail+1:,}번 이후에 {len(ping)}건 데이터 감지 → 정확한 신규 건수 탐색 시작..."
            )

    if known_tail == 0:
        first_page = await engine._fetch_page(1, PAGE_SIZE)
        if not first_page:
            logger.info(f"[{svc}][전략B] Pre-check: 데이터 없음 (tail=0)")
            state = {"last_total_count": 0, "pivots": {}}
            engine.state_repo.save_state(svc, state)
            return 0
        if len(first_page) < PAGE_SIZE:
            final_tail = len(first_page)
            logger.info(f"[{svc}][전략B] Pre-check: 소규모 데이터 감지 — tail={final_tail:,}건 (< PAGE_SIZE={PAGE_SIZE:,}). 지수점프 스킵.")
            logger.info(f"[{svc}][Bootstrapper] Tail 확정: {final_tail:,}")
            return final_tail
        logger.debug(f"[{svc}][전략B] Pre-check: 정상 규모 ({PAGE_SIZE:,}건) → 지수점프 진행")

    # 지수점프
    start_pos = max(PAGE_SIZE, known_tail + PAGE_SIZE)
    pos = start_pos
    last_nonempty = pos
    while not shutdown_event.is_set():
        rows = await engine._fetch_page(pos, pos + PAGE_SIZE - 1)
        if rows:
            last_nonempty = pos
            logger.info(f"[{svc}][Bootstrapper] 지수점프 {pos:,}: {len(rows)}건")
            pos *= 2
            if pos > 50_000_000:
                break
        else:
            break

    low, high = last_nonempty, pos
    logger.info(f"[{svc}][Bootstrapper] 이진탐색 범위: {low:,} ~ {high:,}")

    # 이진탐색
    best_start = low
    while high - low >= PAGE_SIZE and not shutdown_event.is_set():
        mid = ((low + high) // 2 // PAGE_SIZE) * PAGE_SIZE
        if await engine._fetch_page(mid, mid + PAGE_SIZE - 1):
            best_start = mid
            low = mid + PAGE_SIZE
        else:
            high = mid

    # Gap 허용 선형 스캔
    MAX_GAP_PAGES = 3
    pos, page_tail, consecutive_empty = best_start, best_start, 0
    while not shutdown_event.is_set():
        rows = await engine._fetch_page(pos, pos + PAGE_SIZE - 1)
        if rows:
            page_tail = pos + len(rows) - 1
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty >= MAX_GAP_PAGES:
                break
        pos += PAGE_SIZE

    # 정밀화
    page_start = (page_tail // PAGE_SIZE) * PAGE_SIZE + 1
    final_tail = await _precise_tail(engine, page_start, page_tail)

    logger.info(f"[{svc}][Bootstrapper] Tail 확정: {final_tail:,}")
    return final_tail


async def _precise_tail(engine, page_start: int, page_tail_upper: int) -> int:
    """PAGE 경계 내부를 계층적 선형 스캔으로 정확한 tail 확정 (100 -> 10 -> 1단위)."""
    SAFETY = 10
    svc = engine.service_id

    logger.info(
        f"[{svc}][Tail 정밀화] 시작: {page_start:,}~{page_tail_upper:,} "
        f"(범위 {page_tail_upper - page_start + 1}개) — 최대 ~60회 API"
    )

    # Phase A: 100-unit 선형 스캔
    last_nonempty_100 = page_start
    pos = page_start
    while pos <= page_tail_upper and not shutdown_event.is_set():
        end = min(pos + 99, page_tail_upper)
        if await engine._fetch_page(pos, end):
            last_nonempty_100 = pos
        pos += 100

    # Phase B: 10-unit 선형 스캔
    search_end_b = min(last_nonempty_100 + 199, page_tail_upper)
    last_nonempty_10 = last_nonempty_100
    pos = last_nonempty_100
    while pos <= search_end_b and not shutdown_event.is_set():
        end = min(pos + 9, page_tail_upper)
        if await engine._fetch_page(pos, end):
            last_nonempty_10 = pos
        pos += 10

    # Phase C: 1-unit 순차 스캔
    exact_tail = last_nonempty_10 - 1
    scan_end = min(last_nonempty_10 + 19 + SAFETY, page_tail_upper + SAFETY)
    consecutive_empty = 0

    for idx in range(last_nonempty_10, scan_end + 1):
        if shutdown_event.is_set():
            break
        row = await engine._fetch_single(idx)
        if row:
            exact_tail = idx
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty >= SAFETY:
                break

    logger.info(
        f"[{svc}][Tail 정밀화] 완료: exact={exact_tail:,} (PAGE 추정={page_tail_upper:,})"
    )
    return exact_tail


async def bootstrap(engine):
    """처음부터 피벗을 생성하고 정합성을 검증합니다."""
    svc = engine.service_id
    total_count = await find_true_tail(engine, known_tail=0)
    pivots = {}

    logger.info(f"[{svc}][Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
    pivot_indices = list(range(settings.PIVOT_INTERVAL, total_count, settings.PIVOT_INTERVAL))

    semaphore = asyncio.Semaphore(BOOTSTRAP_SEMAPHORE_LIMIT)

    async def _fetch_pivot(idx: int):
        async with semaphore:
            rows = await engine._fetch_page(idx, idx + PAGE_SIZE - 1)
        if rows:
            from app.services.pivot_manager import compute_page_fingerprint
            row = rows[0]
            last_row = rows[-1]
            return idx, {
                "LCNS_NO": row.get("LCNS_NO", ""),
                "CHNG_DT": row.get("CHNG_DT", ""),
                "LAST_LCNS_NO": last_row.get("LCNS_NO", ""),
                "LAST_CHNG_DT": last_row.get("CHNG_DT", ""),
                "BSSH_NM": row.get("BSSH_NM", ""),
                "fingerprint": compute_page_fingerprint(rows),
            }
        return idx, None

    results = await asyncio.gather(*[_fetch_pivot(idx) for idx in pivot_indices])
    for idx, pivot_data in results:
        if pivot_data:
            pivots[str(idx)] = pivot_data

    state = {
        "last_total_count": total_count,
        "pivots": pivots,
        "empty_pivot_cycles": 0,
        "cb_consecutive_count": 0,
    }
    engine.state_repo.save_state(svc, state)
    logger.info(f"[{svc}][Bootstrapper] 부트스트랩 완료! 주 {len(pivots)}개 피벗 색인 생성. (Tail: {total_count:,}건)")

    # Bootstrap 완료 후 Tail 재조회
    logger.info(f"[{svc}] 🔍 Bootstrap 완료 후 Tail 재확인 중...")
    try:
        post_tail = await find_true_tail(engine, known_tail=total_count)
        if post_tail > total_count:
            logger.info(
                f"[{svc}] 📌 Bootstrap 진행 중 {post_tail - total_count:,}건 추가 발생 감지 "
                f"→ last_total_count를 {post_tail:,}으로 업데이트 (다음 주기 Delta 수집 보장)"
            )
            state["last_total_count"] = post_tail
            engine.state_repo.save_state(svc, state)
        else:
            logger.info(f"[{svc}] ✅ Bootstrap 완료 후 Tail 변동 없음.")
    except Exception as e:
        logger.warning(f"[{svc}] Bootstrap 후 Tail 재확인 실패 (무시): {e}")

    # Bootstrap 직후 피벗 즉시 재검증 (경량 모드)
    from app.services import pivot_manager
    changed, _ = await pivot_manager.sample_check(
        state["pivots"], engine.api_client, svc,
        sample_ratio=0.05, max_samples=5
    )
    if changed:
        logger.warning(
            f"[{svc}] ⚠️ Bootstrap 직후 피벗 불일치 감지 (Bootstrap 중 API 변동됨). "
            f"피벗 초기화 → 다음 주기에 Ping만으로 정상 탐색."
        )
        state["pivots"] = {}
        engine.state_repo.save_state(svc, state)
    else:
        logger.info(f"[{svc}] ✅ Bootstrap 피벗 정합성 검증 완료.")
    
    engine._empty_pivot_cycles = 0
    engine._cb_consecutive_count = 0
    return state
