import asyncio
import threading
from app.core.config import settings
from app.core.logger import logger
from app.services import pivot_manager
from app.services.crawler_constants import _GLOBAL_BOOTSTRAP_SEMAPHORE, BOOTSTRAP_SEMAPHORE_LIMIT, PAGE_SIZE
from app.services.api_utils import fetch_page
from app.services.tail_explorer import TailExplorer

class DiffBootstrapper:
    def __init__(self, api_client, service_id: str, state_repo):
        self.api_client = api_client
        self.service_id = service_id
        self.state_repo = state_repo
        self.tail_explorer = TailExplorer(api_client, service_id, state_repo)

    async def _run_bootstrap_standalone(self) -> None:
        logger.info(f"[{self.service_id}] 🔄 Bootstrap 스레드 시작 — 전역 Bootstrap Semaphore 대기 중...")
        acquired = _GLOBAL_BOOTSTRAP_SEMAPHORE.acquire(timeout=3600)
        if not acquired:
            logger.error(f"[{self.service_id}] ❌ Bootstrap Semaphore 대기 시간 초과 (1시간). _bootstrapping 플래그 해제 후 다음 주기에 재시도.")
            try:
                state = self.state_repo.load_state(self.service_id)
                state.pop("_bootstrapping", None)
                self.state_repo.save_state(self.service_id, state)
            except Exception:
                pass
            return

        logger.info(f"[{self.service_id}] 🔄 Bootstrap 스레드 시작 (독립 ApiClient 사용, 직렬화 진행 중)")
        from app.clients.foodsafety_api import ApiClient as _ApiClient
        try:
            async with _ApiClient() as fresh_client:
                original_client = self.api_client
                self.api_client = fresh_client
                self.tail_explorer.api_client = fresh_client
                try:
                    await self.bootstrap()
                except Exception as e:
                    logger.error(f"[{self.service_id}] ❌ Bootstrap 스레드 오류: {e}", exc_info=True)
                    try:
                        state = self.state_repo.load_state(self.service_id)
                        state.pop("_bootstrapping", None)
                        self.state_repo.save_state(self.service_id, state)
                        logger.warning(f"[{self.service_id}] ⚠️ Bootstrap 실패 — _bootstrapping 플래그 해제. 다음 주기에 재시도합니다.")
                    except Exception as cleanup_err:
                        logger.error(f"[{self.service_id}] 플래그 해제 실패: {cleanup_err}")
                finally:
                    self.api_client = original_client
                    self.tail_explorer.api_client = original_client
        finally:
            _GLOBAL_BOOTSTRAP_SEMAPHORE.release()
            logger.info(f"[{self.service_id}] 🔓 Bootstrap Semaphore 해제 — 다음 서비스 Bootstrap 가능")

    async def bootstrap(self):
        total_count = await self.tail_explorer.find_true_tail(known_tail=0)
        pivots = {}

        logger.info(f"[{self.service_id}][Bootstrapper] 피벗 캐싱 시작 (간격: {settings.PIVOT_INTERVAL})...")
        pivot_indices = list(range(settings.PIVOT_INTERVAL, total_count, settings.PIVOT_INTERVAL))

        semaphore = asyncio.Semaphore(BOOTSTRAP_SEMAPHORE_LIMIT)

        async def _fetch_pivot(idx: int):
            async with semaphore:
                rows = await fetch_page(self.api_client, self.service_id, idx, idx + PAGE_SIZE - 1)
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
        self.state_repo.save_state(self.service_id, state)
        logger.info(f"[{self.service_id}][Bootstrapper] 부트스트랩 완료! 주 {len(pivots)}개 피벗 색인 생성. (Tail: {total_count:,}건)")

        logger.info(f"[{self.service_id}] 🔍 Bootstrap 완료 후 Tail 재확인 중...")
        try:
            post_tail = await self.tail_explorer.find_true_tail(known_tail=total_count)
            if post_tail > total_count:
                logger.info(f"[{self.service_id}] 📌 Bootstrap 진행 중 {post_tail - total_count:,}건 추가 발생 감지 → last_total_count를 {post_tail:,}으로 업데이트 (다음 주기 Delta 수집 보장)")
                state["last_total_count"] = post_tail
                self.state_repo.save_state(self.service_id, state)
            else:
                logger.info(f"[{self.service_id}] ✅ Bootstrap 완료 후 Tail 변동 없음.")
        except Exception as e:
            logger.warning(f"[{self.service_id}] Bootstrap 후 Tail 재확인 실패 (무시): {e}")

        changed, _ = await pivot_manager.sample_check(
            state["pivots"], self.api_client, self.service_id,
            sample_ratio=0.05, max_samples=5
        )
        if changed:
            logger.warning(f"[{self.service_id}] ⚠️ Bootstrap 직후 피벗 불일치 감지 (Bootstrap 중 API 변동됨). 피벗 초기화 → 다음 주기에 Ping만으로 정상 탐색.")
            state["pivots"] = {}
            self.state_repo.save_state(self.service_id, state)
        else:
            logger.info(f"[{self.service_id}] ✅ Bootstrap 피벗 정합성 검증 완료.")
            
        return state

    async def _fetch_today_補完(self, today_str: str) -> list:
        svc = self.service_id
        rows_found = []
        for key in self.api_client._key_pool:
            url = (
                f"https://openapi.foodsafetykorea.go.kr/api/{key}/{svc}/json/1/1000"
                f"?CHNG_DT={today_str}"
            )
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        data = await resp.json(content_type=None)
                block = data.get(svc, {})
                code = block.get("RESULT", {}).get("CODE", "")
                if code == "INFO-300":
                    continue
                rows = block.get("row", [])
                if rows:
                    rows_found.extend(rows)
                    total_str = block.get("total_count", "0")
                    total = int(total_str) if str(total_str).isdigit() else 0
                    logger.info(f"[{svc}] 📅 오늘({today_str}) CHNG_DT 직접 조회: {len(rows)}건 수신 (total={total})")
                    if total > 1000:
                        page = 2
                        while (page - 1) * 1000 < total:
                            st = (page - 1) * 1000 + 1
                            ed = page * 1000
                            url2 = (
                                f"https://openapi.foodsafetykorea.go.kr/api/{key}/{svc}/json/{st}/{ed}"
                                f"?CHNG_DT={today_str}"
                            )
                            async with session.get(url2, timeout=aiohttp.ClientTimeout(total=15)) as r2:
                                d2 = await r2.json(content_type=None)
                            rows2 = d2.get(svc, {}).get("row", [])
                            if not rows2:
                                break
                            rows_found.extend(rows2)
                            page += 1
                break
            except Exception as e:
                logger.debug(f"[{svc}] 오늘 보완 조회 실패 (키 {key[:6]}): {e}")
                continue
        return rows_found
