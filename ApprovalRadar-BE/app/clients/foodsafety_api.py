# pyrefly: ignore [missing-import]
import asyncio
# pyrefly: ignore [missing-import]
import httpx
import time
import threading
import datetime
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event

from app.clients.key_manager import KeyManager, ApiKeysExhaustedError
from app.clients.response_handler import ResponseHandler
from app.clients.waf_strategy import WafStrategy

class ApiClient:
    # 하위 호환성을 위한 클래스 메소드 래핑
    @classmethod
    def is_exhausted(cls) -> bool:
        return KeyManager.is_exhausted()

    @classmethod
    def mark_exhausted(cls):
        KeyManager.mark_exhausted()

    @classmethod
    def recover_exhaustion(cls, active_masked_keys: set[str]) -> None:
        KeyManager.recover_exhaustion(active_masked_keys)

    @classmethod
    async def check_key_recovery(cls, api_keys: list, base_url: str, data_type: str, service_id: str = "I2859") -> bool:
        return await KeyManager.check_key_recovery(api_keys, base_url, data_type, service_id)

    def __init__(self):
        self.key_manager = KeyManager()
        self._session = self._create_session()
        self._call_count: int = 0

    @staticmethod
    def _create_session() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={'Connection': 'keep-alive', 'Accept': 'application/json'},
            follow_redirects=True,
        )

    async def _renew_session(self):
        try:
            await self._session.aclose()
        except Exception:
            pass
        self._session = self._create_session()

    async def aclose(self):
        try:
            await self._session.aclose()
        except Exception:
            pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    def get_current_key(self) -> str:
        return self.key_manager.get_current_key()

    async def rotate_key(self, failed_key: str):
        await self.key_manager.rotate_key(failed_key, self._renew_session)

    async def switch_key(self, current_key: str):
        await self.key_manager.switch_key(current_key, self._renew_session)

    async def fetch_data(self, service_id: str, start_idx: int, end_idx: int, max_retries: int = 5, timeout: int = 30, **kwargs) -> dict:
        now_ts = time.time()
        if now_ts - self.key_manager._last_refresh_time > KeyManager._REFRESH_INTERVAL:
            self.key_manager.refresh_keys()
            self.key_manager._last_refresh_time = now_ts

        self._call_count += 1
        if KeyManager.is_exhausted():
            raise ApiKeysExhaustedError("All API keys are exhausted for today.")

        attempt = 0
        waf_retries = 0
        backoff = 1.0
        response = None
        sem_acquired = False
        current_sem = None

        loop = asyncio.get_event_loop()

        while attempt < max_retries and not shutdown_event.is_set():
            api_key = self.get_current_key()
            
            # I2861 호출 시 가짜 파라미터를 무조건 강제 적용하여 실시간 Live View 활성화
            if service_id == "I2861":
                if not kwargs:
                    kwargs = {"SYS_SYNC": "LIVE"}
                elif "SYS_SYNC" not in kwargs:
                    kwargs["SYS_SYNC"] = "LIVE"

            url = f"{settings.BASE_URL}/{api_key}/{service_id}/{settings.DATA_TYPE}/{start_idx}/{end_idx}"
            if kwargs:
                url += "/" + "&".join(f"{k}={v}" for k, v in kwargs.items())

            sem = WafStrategy.get_key_semaphore(api_key)
            await loop.run_in_executor(None, sem.acquire)
            current_sem = sem
            sem_acquired = True

            try:
                if self.get_current_key() != api_key:
                    sem.release()
                    sem_acquired = False
                    current_sem = None
                    continue

                try:
                    response = await self._session.get(url, timeout=timeout)
                    response.raise_for_status()
                    res = response.json()

                    if service_id in res:
                        result = ResponseHandler.handle_api_response_code(
                            res, service_id, api_key, self.key_manager, self.key_manager.current_key_idx
                        )
                        if result is not None:
                            if isinstance(result, dict) and result.get("__rotate_key__"):
                                sem.release()
                                sem_acquired = False
                                await self.rotate_key(api_key)
                                logger.warning(f"키 회전 후 {settings.GAP_SECONDS}초 대기...")
                                await asyncio.sleep(settings.GAP_SECONDS)
                                continue
                            sem.release()
                            sem_acquired = False
                            return result

                        if shutdown_event.is_set():
                            return {}
                        backoff = await WafStrategy.sleep_backoff(backoff)
                        attempt += 1
                    else:
                        logger.warning(f"알 수 없는 응답 형식입니다. {backoff}초 후 재시도합니다...")
                        backoff = await WafStrategy.sleep_backoff(backoff)
                        attempt += 1

                except ValueError as e:
                    raw_text = response.text if response is not None else ""
                    is_waf_block = "현재 접속 중인 인증키입니다" in raw_text

                    ResponseHandler.handle_value_error(e, api_key, service_id, kwargs, response, self.key_manager)

                    if is_waf_block:
                        waf_retries += 1
                        waf_wait = min(WafStrategy._WAF_WAIT_STEP * waf_retries, WafStrategy._WAF_WAIT_CAP)
                        logger.warning(
                            f"WAF 임시 차단 감지! 키 전환 후 {waf_wait:.0f}초 대기 "
                            f"(WAF재시도 {waf_retries}/{WafStrategy._MAX_WAF_RETRIES}회) — "
                            f"attempt 카운트 유지 ({attempt}/{max_retries})"
                        )
                        sem.release()
                        sem_acquired = False
                        await self.switch_key(api_key)
                        await asyncio.sleep(waf_wait)

                        if waf_retries >= WafStrategy._MAX_WAF_RETRIES:
                            logger.warning(f"WAF 재시도 {waf_retries}회 초과 → attempt 카운트 소모로 전환")
                            attempt += 1
                            waf_retries = 0
                    else:
                        sem.release()
                        sem_acquired = False
                        await self.switch_key(api_key)
                        backoff = await WafStrategy.sleep_backoff(backoff)
                        attempt += 1

                except httpx.TimeoutException:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    logger.warning(f"[읽기 타임아웃] {ctx} | 서버 응답 지연 ({timeout}초 초과). {backoff}초 후 재시도합니다.")
                    backoff = await WafStrategy.sleep_backoff(backoff)
                    attempt += 1

                except httpx.HTTPError as e:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    if kwargs:
                        ctx += f", 추가:{kwargs}"
                    logger.warning(f"[네트워크 통신 오류] {ctx} | 사유: {str(e)}. 연결 오류로 인해 키를 전환합니다.")
                    sem.release()
                    sem_acquired = False
                    await self.switch_key(api_key)
                    backoff = await WafStrategy.sleep_backoff(backoff)
                    attempt += 1

            finally:
                if sem_acquired and current_sem is not None:
                    current_sem.release()
                    sem_acquired = False

        logger.error(f"❌ 최대 재시도 횟수({max_retries}) 초과. API 요청 완전 실패: {start_idx}~{end_idx}")
        raise Exception(f"식품나라 API 서버 통신 실패 (최대 재시도 초과): {start_idx}~{end_idx}")

    def get_total_call_count(self) -> int:
        return self._call_count

    async def check_keys_status(self, service_id: str = "I2861"):
        await self.key_manager.check_keys_status(service_id)
