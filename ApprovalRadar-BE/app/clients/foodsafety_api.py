# pyrefly: ignore [missing-import]
import asyncio
# pyrefly: ignore [missing-import]
import httpx
import threading
import datetime
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event
from app.clients import key_usage_repository as key_usage_repo


class ApiKeysExhaustedError(Exception):
    """모든 API 키가 소진되었을 때 발생하는 예외"""
    pass


class ApiClient:
    # ─── 클래스 레벨 공유 상태 (모든 인스턴스 공유) ──────────────────────────
    _exhausted_until: datetime.datetime | None = None
    _class_lock = threading.Lock()
    # key_masked → {"date": "YYYY-MM-DD", "count": int}
    _usage: dict[str, dict] = {}
    # ✅ 키 회복 체크용 공유 AsyncClient (클래스 레벨)
    _recovery_client: "httpx.AsyncClient | None" = None

    # ─── 내부 유틸리티 ──────────────────────────────────────────────────────

    @staticmethod
    def _mask_key(key: str) -> str:
        """API 키를 마스킹하여 반환합니다."""
        return f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"

    # ─── 클래스 레벨 상태 관리 ──────────────────────────────────────────────

    @classmethod
    def is_exhausted(cls) -> bool:
        """소진 상태인지 확인. 자정이 지났으면 자동 초기화."""
        with cls._class_lock:
            if cls._exhausted_until is None:
                return False
            if datetime.datetime.now() >= cls._exhausted_until:
                cls._exhausted_until = None
                logger.info("🔄 자정이 지나 API 키 소진 상태가 초기화되었습니다. 크롤링을 재개합니다.")
                return False
            return True

    @classmethod
    def mark_exhausted(cls):
        """모든 키 소진. 10분 후 재시도 가능 상태로 마크 (자정 고정 X → 일찍 회복 시 즉시 재개)."""
        with cls._class_lock:
            now = datetime.datetime.now()
            # 10분 후에 다시 체크. key_recovery_job이 10분마다 실제 API 찔러봄
            cls._exhausted_until = now + datetime.timedelta(minutes=10)

    @classmethod
    def _increment_usage(cls, key: str, service_id: str = ""):
        """키별 오늘 사용량 +1. DB에도 upsert. 서비스명 포함 로그 출력."""
        today = datetime.date.today().isoformat()
        masked = cls._mask_key(key)
        with cls._class_lock:
            entry = cls._usage.setdefault(masked, {"date": today, "count": 0})
            if entry["date"] != today:
                entry["date"] = today
                entry["count"] = 0
            entry["count"] += 1
            today_count = entry["count"]
        key_usage_repo.increment(masked, today, service_id)

        # 서비스명 포함 로그
        svc_name = key_usage_repo.SERVICE_NAME_MAP.get(service_id, service_id) if service_id else "알 수 없음"
        logger.debug(
            f"[API 호출] {svc_name}({service_id}) | 키: {masked} | 오늘 누적: {today_count}회"
        )

        # 잔여량 경고: 900회 이상 사용 시 WARN SSE 브로드캐스트 (100회 단위 1회)
        if today_count in (900, 950, 990):
            try:
                from app.core.events import broadcaster
                import json
                warn_msg = json.dumps({
                    "type": "WARN",
                    "message": f"API 키 잔여량 경고: {masked} 키가 {today_count}/1000건 사용됨 — 잔여 {1000 - today_count}건"
                }, ensure_ascii=False)
                broadcaster.broadcast_sync(warn_msg)
            except Exception:
                pass

    @classmethod
    def _mark_key_exhausted_in_db(cls, key: str):
        """DB에서 해당 키를 exhausted=1, call_count=1000으로 마크."""
        today = datetime.date.today().isoformat()
        key_usage_repo.mark_exhausted(cls._mask_key(key), today)

    @classmethod
    def recover_exhaustion(cls, active_masked_keys: set[str]) -> None:
        """소진 상태에서 회복된 키 목록을 받아 서버 상태를 초기화합니다."""
        today = datetime.date.today().isoformat()
        with cls._class_lock:
            cls._exhausted_until = None
        for masked in active_masked_keys:
            key_usage_repo.reset(masked, today)

    @classmethod
    async def check_key_recovery(cls, api_keys: list, base_url: str, data_type: str, service_id: str = "I2859") -> bool:
        """
        소진 상태일 때만 호출. 실제 API를 호출해 회복된 키가 있으면 recover_exhaustion()을 호출.
        ✅ httpx.AsyncClient 재사용으로 TCP 핸드셰이크 오버헤드 제거.
        Returns: 회복 여부 (True = 하나 이상 활성 키 발견)
        """
        if not cls.is_exhausted():
            return False

        # 회복 클라이언트 재사용: 없거나 closed 상태면 새로 생성
        with cls._class_lock:
            if cls._recovery_client is None or cls._recovery_client.is_closed:
                cls._recovery_client = cls._create_session()

        logger.info("[키 회복 체크] 소진된 키 활성화 여부 확인 중...")
        active_masked: set[str] = set()
        for key in api_keys:
            url = f"{base_url}/{key}/{service_id}/{data_type}/1/1"
            try:
                res = (await cls._recovery_client.get(url, timeout=7)).json()
                if service_id in res:
                    code = res[service_id]['RESULT']['CODE']
                    if code == "INFO-000":
                        active_masked.add(cls._mask_key(key))
            except Exception:
                pass

        if active_masked:
            cls.recover_exhaustion(active_masked)
            logger.info(f"키 회복: {len(active_masked)}개 키가 정상화됨. 다음 크롤링 주기에 자동 재개됩니다.")
            return True

        logger.info("[키 회복 체크] 아직 소진 상태 유지 중.")
        return False

    # ─── 인스턴스 초기화 ────────────────────────────────────────────────────

    def __init__(self):
        # 매 생성 시 DB에서 최신 키 리로드 (런타임 중 추가된 키 즉시 반영)
        settings._load_api_keys()
        self.api_keys = settings.API_KEYS.copy()
        self.current_key_idx = 0
        self.key_lock = threading.Lock()
        self.exhausted_keys = set()
        # WAF 동시 접근 방지: 키별 요청 직렬화 Lock
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._session = self._create_session()
        # 이 세션에서의 총 API 호출 횟수 카운터 (CLI 보고용)
        self._call_count: int = 0

    def refresh_keys(self):
        """DB에서 최신 API 키 리스트를 리프레시합니다.
        런타임 중 추가/삭제된 키를 반영합니다."""
        settings._load_api_keys()
        new_keys = settings.API_KEYS.copy()
        with self.key_lock:
            old_keys = set(self.api_keys)
            new_set = set(new_keys)
            added = new_set - old_keys
            removed = old_keys - new_set

            if added or removed:
                self.api_keys = new_keys
                # 제거된 키가 있으면 exhausted에서도 제거
                self.exhausted_keys -= removed
                # 인덱스 보정
                if self.current_key_idx >= len(self.api_keys):
                    self.current_key_idx = 0
                if added:
                    logger.info(
                        f"🔑 [키 리프레시] {len(added)}개 키 추가 감지 → "
                        f"총 {len(self.api_keys)}개 활성 (소진: {len(self.exhausted_keys)}개)"
                    )
                if removed:
                    logger.info(
                        f"🔑 [키 리프레시] {len(removed)}개 키 제거 감지"
                    )

    @staticmethod
    def _create_session() -> httpx.AsyncClient:
        """HTTP Keep-Alive 연결 재사용 AsyncClient 세션을 생성합니다."""
        return httpx.AsyncClient(
            headers={'Connection': 'keep-alive', 'Accept': 'application/json'},
            follow_redirects=True,
        )

    async def _renew_session(self):
        """세션을 새로 생성합니다. 키 교체 시 호출됩니다."""
        try:
            await self._session.aclose()
        except Exception:
            pass
        self._session = self._create_session()

    async def aclose(self):
        """AsyncClient 세션을 종료합니다. async with ApiClient() 사용 시 자동 호출됩니다."""
        try:
            await self._session.aclose()
        except Exception:
            pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    # ─── 키 관리 ────────────────────────────────────────────────────────────

    def get_current_key(self) -> str:
        with self.key_lock:
            return self.api_keys[self.current_key_idx]

    async def rotate_key(self, failed_key: str):
        """한도 초과 키를 소진 목록에 추가하고 다음 활성 키로 교체합니다.
        소진된 키는 건너뛰어 retry 낭비를 방지합니다."""
        with self.key_lock:
            self.exhausted_keys.add(failed_key)
            ApiClient._mark_key_exhausted_in_db(failed_key)

            if len(self.exhausted_keys) >= len(self.api_keys):
                ApiClient.mark_exhausted()
                logger.error("🚨 [긴급] 오늘자 식품나라 API 키가 모두 소진되었습니다. 크롤링이 중단됩니다.")
                raise ApiKeysExhaustedError("All API keys are exhausted for today.")

            if self.api_keys[self.current_key_idx] != failed_key:
                return

            # 소진된 키를 건너뛰고 활성 키로 바로 점프
            for _ in range(len(self.api_keys)):
                self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
                candidate = self.api_keys[self.current_key_idx]
                if candidate not in self.exhausted_keys:
                    logger.info(f"[키 회전] API 한도 초과! 활성 키로 교체: {candidate[:5]}***")
                    break
            else:
                # 이론적으로 여기 도달 불가 (위 exhausted_keys 체크에서 걸림)
                raise ApiKeysExhaustedError("All API keys are exhausted for today.")
        await self._renew_session()

    async def switch_key(self, current_key: str):
        """한도 초과가 아닌 일시적 문제(WAF 임시차단)로 키를 소진시키지 않고 다음 키로 단순 변경합니다."""
        with self.key_lock:
            if self.api_keys[self.current_key_idx] != current_key:
                return
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_key_idx]
            logger.info(f"[키 전환] 일시적 오류(WAF/Timeout)로 임시 키 전환: {new_key[:5]}***")
        await self._renew_session()

    # ─── API 호출 및 에러 처리 ──────────────────────────────────────────────

    def _handle_api_response_code(self, res: dict, service_id: str, api_key: str) -> dict | None:
        """
        API 응답 코드를 분석합니다.
        - 정상: 응답 dict 반환
        - 키 회전/재시도 필요: None 반환
        - 복구 불가 오류: dict 반환 (상위에서 그대로 반환)
        Raises: ApiKeysExhaustedError
        """
        code = res[service_id]['RESULT']['CODE']
        msg = res[service_id]['RESULT']['MSG']

        if code in ("INFO-000", "INFO-200"):
            ApiClient._increment_usage(api_key, service_id)
            return res


        if code in ("INFO-300", "INFO-333") or "유효 호출건수" in msg:
            # rotate_key는 async → 상위 fetch_data에서 처리 (마커 반환)
            return {"__rotate_key__": True}

        if code in ("ERROR-500", "ERROR-601"):
            logger.warning(f"[API 서버 오류] {code}: {msg}.")
            return None  # 재시도 신호 (백오프는 상위에서 처리)

        logger.error(f"[API 파라미터/기타 오류] {code}: {msg}")
        return res  # 복구 불가, 그대로 반환

    def _handle_value_error(self, e: Exception, api_key: str, service_id: str, kwargs: dict, response) -> None:
        """JSON 파싱 실패(WAF 차단 의심)를 처리합니다. (동기 — I/O 없음)"""
        ctx = f"서비스:{service_id}, 추가:{kwargs}" if kwargs else f"서비스:{service_id}"
        raw_text = response.text[:200].replace('\n', ' ') if response is not None else "N/A"
        logger.warning(
            f"[API 파싱 오류] {ctx} | WAF 차단 의심. 미리보기: {raw_text} | 사유: {str(e)}"
        )
        if "현재 접속 중인 인증키입니다" in raw_text:
            logger.warning("WAF 임시 차단 감지! 키를 즉시 전환합니다.")

    @staticmethod
    async def _sleep_backoff(backoff: float) -> float:
        """지수 백오프 sleep 후 다음 backoff 값(최대 10초)을 반환합니다."""
        await asyncio.sleep(backoff)
        return min(backoff * 2, 10)

    async def fetch_data(self, service_id: str, start_idx: int, end_idx: int, max_retries: int = 5, timeout: int = 30, **kwargs) -> dict:
        """
        주어진 구간의 데이터를 비동기로 조회합니다.
        - 한도 초과(INFO-300 등) 시 자동으로 키를 회전하고 재시도합니다.
        - 서버 에러(ERROR-500 등)나 네트워크 에러 발생 시 지수 백오프를 적용하여 재시도합니다.
        """
        self._call_count += 1  # 호출 횟수 카운터
        if ApiClient.is_exhausted():
            raise ApiKeysExhaustedError("All API keys are exhausted for today.")

        attempt = 0
        backoff = 1.0
        response = None

        while attempt < max_retries and not shutdown_event.is_set():
            api_key = self.get_current_key()
            url = f"{settings.BASE_URL}/{api_key}/{service_id}/{settings.DATA_TYPE}/{start_idx}/{end_idx}"
            if kwargs:
                url += "/" + "&".join(f"{k}={v}" for k, v in kwargs.items())

            # 키별 asyncio.Lock — 동일 키 동시 요청 WAF 차단 방지
            if api_key not in self._key_locks:
                self._key_locks[api_key] = asyncio.Lock()
            key_lock = self._key_locks[api_key]

            async with key_lock:
                if self.get_current_key() != api_key:
                    continue  # 키 교체됨 → 재시도 (attempt 소모 없음)

                try:
                    response = await self._session.get(url, timeout=timeout)
                    response.raise_for_status()
                    res = response.json()

                    if service_id in res:
                        result = self._handle_api_response_code(res, service_id, api_key)
                        if result is not None:
                            # 키 회전 마커 확인
                            if isinstance(result, dict) and result.get("__rotate_key__"):
                                await self.rotate_key(api_key)
                                logger.warning(f"키 회전 후 {settings.GAP_SECONDS}초 대기...")
                                await asyncio.sleep(settings.GAP_SECONDS)
                                # attempt 증가 없이 continue — 키 소진은 retry가 아님
                                # (모든 키 소진 시 rotate_key가 ApiKeysExhaustedError 발생)
                                continue
                            return result
                        # None → 재시도 (서버 오류)
                        if shutdown_event.is_set():
                            return {}
                        backoff = await self._sleep_backoff(backoff)
                        attempt += 1
                    else:
                        logger.warning(f"알 수 없는 응답 형식입니다. {backoff}초 후 재시도합니다...")
                        backoff = await self._sleep_backoff(backoff)
                        attempt += 1

                except ValueError as e:
                    self._handle_value_error(e, api_key, service_id, kwargs, response)
                    await self.switch_key(api_key)
                    backoff = await self._sleep_backoff(backoff)
                    attempt += 1

                except httpx.TimeoutException:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    logger.warning(f"[읽기 타임아웃] {ctx} | 서버 응답 지연 ({timeout}초 초과). {backoff}초 후 재시도합니다.")
                    backoff = await self._sleep_backoff(backoff)
                    attempt += 1

                except httpx.HTTPError as e:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    if kwargs:
                        ctx += f", 추가:{kwargs}"
                    logger.warning(f"[네트워크 통신 오류] {ctx} | 사유: {str(e)}. 연결 오류로 인해 키를 전환합니다.")
                    await self.switch_key(api_key)
                    backoff = await self._sleep_backoff(backoff)
                    attempt += 1

        logger.error(f"❌ 최대 재시도 횟수({max_retries}) 초과. API 요청 완전 실패: {start_idx}~{end_idx}")
        raise Exception(f"식품나라 API 서버 통신 실패 (최대 재시도 초과): {start_idx}~{end_idx}")

    # ─── 키 상태 점검 ───────────────────────────────────────────────────────

    def get_total_call_count(self) -> int:
        """이 ApiClient 세션에서 발생한 총 API 호출 횟수를 반환합니다. (CLI 보고용)"""
        return self._call_count

    async def check_keys_status(self, service_id: str = "I2859"):
        """모든 로드된 API 키의 상태를 테스트하여 출력합니다."""
        logger.info(f"\n--- API 키 상태 점검 시작 (총 {len(self.api_keys)}개) ---")

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for idx, key in enumerate(self.api_keys):
                masked_key = self._mask_key(key)
                url = f"{settings.BASE_URL}/{key}/{service_id}/{settings.DATA_TYPE}/1/1"

                try:
                    res = (await client.get(url, timeout=5)).json()
                    if service_id in res:
                        code = res[service_id]['RESULT']['CODE']
                        msg = res[service_id]['RESULT']['MSG']
                        if code == "INFO-000":
                            status = "[정상 동작 (Active)]"
                        elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in msg:
                            status = "[일일 한도 초과 (Exhausted)]"
                        else:
                            status = f"[오류 ({code}: {msg})]"
                    else:
                        status = "[알 수 없는 응답 형식]"
                except Exception as e:
                    status = f"[통신 오류 또는 WAF 차단 ({str(e)})]"

                logger.info(f"Key {idx+1} ({masked_key}): {status}")
                await asyncio.sleep(0.5)

        logger.info("--- 점검 완료 ---\n")
