import requests
import threading
import datetime
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event


class ApiKeysExhaustedError(Exception):
    """모든 API 키가 소진되었을 때 발생하는 예외"""
    pass


class ApiClient:
    # ─── 클래스 레벨 공유 상태 (모든 인스턴스 공유) ──────────────────────────
    _exhausted_until: datetime.datetime | None = None
    _class_lock = threading.Lock()
    # key_masked → {"date": "YYYY-MM-DD", "count": int}
    _usage: dict[str, dict] = {}

    # ─── 내부 유틸리티 ──────────────────────────────────────────────────────

    @staticmethod
    def _mask_key(key: str) -> str:
        """API 키를 마스킹하여 반환합니다."""
        return f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"

    @classmethod
    def _upsert_key_usage(cls, masked: str, today: str, *, exhausted: bool = False, reset: bool = False):
        """api_key_usage 테이블에 사용량을 upsert합니다."""
        try:
            from database import get_db
            with get_db() as conn:
                if exhausted:
                    conn.execute(
                        '''INSERT INTO api_key_usage (key_masked, usage_date, call_count, exhausted, last_updated)
                           VALUES (?, ?, 1000, 1, CURRENT_TIMESTAMP)
                           ON CONFLICT(key_masked, usage_date)
                           DO UPDATE SET call_count=1000, exhausted=1, last_updated=CURRENT_TIMESTAMP''',
                        (masked, today)
                    )
                elif reset:
                    conn.execute(
                        '''INSERT INTO api_key_usage (key_masked, usage_date, call_count, exhausted, last_updated)
                           VALUES (?, ?, 0, 0, CURRENT_TIMESTAMP)
                           ON CONFLICT(key_masked, usage_date)
                           DO UPDATE SET call_count=0, exhausted=0, last_updated=CURRENT_TIMESTAMP''',
                        (masked, today)
                    )
                else:
                    conn.execute(
                        '''INSERT INTO api_key_usage (key_masked, usage_date, call_count, last_updated)
                           VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                           ON CONFLICT(key_masked, usage_date)
                           DO UPDATE SET call_count = call_count + 1, last_updated = CURRENT_TIMESTAMP''',
                        (masked, today)
                    )
                conn.commit()
        except Exception:
            pass  # 사용량 기록 실패는 크롤링에 영향 없음

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
        """오늘 키가 모두 소진됨. 내일 자정까지 소진 상태로 마크."""
        with cls._class_lock:
            now = datetime.datetime.now()
            tomorrow = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            cls._exhausted_until = tomorrow

    @classmethod
    def _increment_usage(cls, key: str):
        """키별 오늘 사용량 +1. DB에도 upsert."""
        today = datetime.date.today().isoformat()
        masked = cls._mask_key(key)
        with cls._class_lock:
            entry = cls._usage.setdefault(masked, {"date": today, "count": 0})
            if entry["date"] != today:
                entry["date"] = today
                entry["count"] = 0
            entry["count"] += 1
        cls._upsert_key_usage(masked, today)

    @classmethod
    def _mark_key_exhausted_in_db(cls, key: str):
        """DB에서 해당 키를 exhausted=1, call_count=1000으로 마크."""
        today = datetime.date.today().isoformat()
        cls._upsert_key_usage(cls._mask_key(key), today, exhausted=True)

    @classmethod
    def recover_exhaustion(cls, active_masked_keys: set[str]) -> None:
        """소진 상태에서 회복된 키 목록을 받아 서버 상태를 초기화합니다."""
        today = datetime.date.today().isoformat()
        with cls._class_lock:
            cls._exhausted_until = None
        for masked in active_masked_keys:
            cls._upsert_key_usage(masked, today, reset=True)

    @classmethod
    def check_key_recovery(cls, api_keys: list, base_url: str, data_type: str, service_id: str = "I2859") -> bool:
        """
        소진 상태일 때만 호출. 실제 API를 호출해 회복된 키가 있으면 recover_exhaustion()을 호출.
        Returns: 회복 여부 (True = 하나 이상 활성 키 발견)
        """
        if not cls.is_exhausted():
            return False

        import requests as req_lib
        logger.info("[키 회복 체크] 소진된 키 활성화 여부 확인 중...")
        active_masked: set[str] = set()
        for key in api_keys:
            url = f"{base_url}/{key}/{service_id}/{data_type}/1/1"
            try:
                res = req_lib.get(url, timeout=7).json()
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
        self.api_keys = settings.API_KEYS.copy()
        self.current_key_idx = 0
        self.key_lock = threading.Lock()
        self.exhausted_keys = set()
        # WAF 동시 접근 방지: 키별 요청 직렬화 Lock
        self._key_locks: dict[str, threading.Lock] = {
            key: threading.Lock() for key in self.api_keys
        }
        self._session = self._create_session()

    @staticmethod
    def _create_session() -> requests.Session:
        """HTTP Keep-Alive 연결 재사용 세션을 생성합니다."""
        session = requests.Session()
        session.headers.update({'Connection': 'keep-alive', 'Accept': 'application/json'})
        return session

    def _renew_session(self):
        """세션을 새로 생성합니다. 키 교체 시 호출됩니다."""
        self._session = self._create_session()

    # ─── 키 관리 ────────────────────────────────────────────────────────────

    def get_current_key(self) -> str:
        with self.key_lock:
            return self.api_keys[self.current_key_idx]

    def rotate_key(self, failed_key: str):
        """한도 초과 키를 소진 목록에 추가하고 다음 키로 교체합니다."""
        with self.key_lock:
            self.exhausted_keys.add(failed_key)
            ApiClient._mark_key_exhausted_in_db(failed_key)

            if len(self.exhausted_keys) >= len(self.api_keys):
                ApiClient.mark_exhausted()
                logger.error("🚨 [긴급] 오늘자 식품나라 API 키가 모두 소진되었습니다. 크롤링이 중단됩니다.")
                raise ApiKeysExhaustedError("All API keys are exhausted for today.")

            if self.api_keys[self.current_key_idx] != failed_key:
                return

            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_key_idx]
            logger.info(f"[키 회전] API 한도 초과! 새로운 키로 교체: {new_key[:5]}***")
            self._renew_session()

    def switch_key(self, current_key: str):
        """한도 초과가 아닌 일시적 문제(WAF 임시차단)로 키를 소진시키지 않고 다음 키로 단순 변경합니다."""
        with self.key_lock:
            if self.api_keys[self.current_key_idx] != current_key:
                return
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            new_key = self.api_keys[self.current_key_idx]
            logger.info(f"[키 전환] 일시적 오류(WAF/Timeout)로 임시 키 전환: {new_key[:5]}***")
            self._renew_session()

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
            ApiClient._increment_usage(api_key)
            return res

        if code in ("INFO-300", "INFO-333") or "유효 호출건수" in msg:
            self.rotate_key(api_key)
            logger.warning(f"키 회전 후 {settings.GAP_SECONDS}초 대기...")
            shutdown_event.wait(settings.GAP_SECONDS)
            return None  # 재시도 신호

        if code in ("ERROR-500", "ERROR-601"):
            logger.warning(f"[API 서버 오류] {code}: {msg}.")
            return None  # 재시도 신호 (백오프는 상위에서 처리)

        logger.error(f"[API 파라미터/기타 오류] {code}: {msg}")
        return res  # 복구 불가, 그대로 반환

    def _handle_value_error(self, e: Exception, api_key: str, service_id: str, kwargs: dict, response) -> None:
        """JSON 파싱 실패(WAF 차단 의심)를 처리합니다."""
        ctx = f"서비스:{service_id}, 추가:{kwargs}" if kwargs else f"서비스:{service_id}"
        raw_text = response.text[:200].replace('\n', ' ') if response is not None else "N/A"
        logger.warning(
            f"[API 파싱 오류] {ctx} | WAF 차단 의심. 미리보기: {raw_text} | 사유: {str(e)}"
        )
        if "현재 접속 중인 인증키입니다" in raw_text:
            logger.warning("WAF 임시 차단 감지! 키를 즉시 전환합니다.")
        self.switch_key(api_key)

    def fetch_data(self, service_id: str, start_idx: int, end_idx: int, max_retries: int = 5, timeout: int = 30, **kwargs) -> dict:
        """
        주어진 구간의 데이터를 조회합니다.
        - 한도 초과(INFO-300 등) 시 자동으로 키를 회전하고 재시도합니다.
        - 서버 에러(ERROR-500 등)나 네트워크 에러 발생 시 지수 백오프를 적용하여 재시도합니다.
        """
        if ApiClient.is_exhausted():
            raise ApiKeysExhaustedError("All API keys are exhausted for today.")

        attempt = 0
        backoff = 1
        response = None

        while attempt < max_retries and not shutdown_event.is_set():
            api_key = self.get_current_key()
            url = f"{settings.BASE_URL}/{api_key}/{service_id}/{settings.DATA_TYPE}/{start_idx}/{end_idx}"
            if kwargs:
                url += "/" + "&".join(f"{k}={v}" for k, v in kwargs.items())

            # 동일 키 동시 요청 → WAF 차단 방지 (키별 직렬화)
            key_lock = self._key_locks.setdefault(api_key, threading.Lock())
            with key_lock:
                if self.get_current_key() != api_key:
                    continue  # 키 교체됨 → 재시도 (attempt 소모 없음)

                try:
                    response = self._session.get(url, timeout=timeout)
                    response.raise_for_status()
                    res = response.json()

                    if service_id in res:
                        result = self._handle_api_response_code(res, service_id, api_key)
                        if result is not None:
                            return result
                        # None → 재시도 (키 회전 또는 서버 오류)
                        if shutdown_event.is_set():
                            return {}
                        backoff = min(backoff * 2, 10)
                        attempt += 1
                    else:
                        logger.warning(f"알 수 없는 응답 형식입니다. {backoff}초 후 재시도합니다...")
                        if shutdown_event.wait(backoff):
                            return {}
                        backoff = min(backoff * 2, 10)
                        attempt += 1

                except ValueError as e:
                    self._handle_value_error(e, api_key, service_id, kwargs, response)
                    if shutdown_event.wait(backoff):
                        return {}
                    backoff = min(backoff * 2, 10)
                    attempt += 1

                except requests.exceptions.Timeout:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    logger.warning(f"[읽기 타임아웃] {ctx} | 서버 응답 지연 ({timeout}초 초과). {backoff}초 후 재시도합니다.")
                    if shutdown_event.wait(backoff):
                        return {}
                    backoff = min(backoff * 2, 10)
                    attempt += 1

                except requests.exceptions.RequestException as e:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    if kwargs:
                        ctx += f", 추가:{kwargs}"
                    logger.warning(f"[네트워크 통신 오류] {ctx} | 사유: {str(e)}. 연결 오류로 인해 키를 전환합니다.")
                    self.switch_key(api_key)
                    if shutdown_event.wait(backoff):
                        return {}
                    backoff = min(backoff * 2, 10)
                    attempt += 1

        logger.error(f"❌ 최대 재시도 횟수({max_retries}) 초과. API 요청 완전 실패: {start_idx}~{end_idx}")
        raise Exception(f"식품나라 API 서버 통신 실패 (최대 재시도 초과): {start_idx}~{end_idx}")

    # ─── 키 상태 점검 ───────────────────────────────────────────────────────

    def check_keys_status(self, service_id: str = "I2859"):
        """모든 로드된 API 키의 상태를 테스트하여 출력합니다."""
        logger.info(f"\n--- API 키 상태 점검 시작 (총 {len(self.api_keys)}개) ---")

        for idx, key in enumerate(self.api_keys):
            masked_key = self._mask_key(key)
            url = f"{settings.BASE_URL}/{key}/{service_id}/{settings.DATA_TYPE}/1/1"

            try:
                res = requests.get(url, timeout=5).json()
                if service_id in res:
                    code = res[service_id]['RESULT']['CODE']
                    msg = res[service_id]['RESULT']['MSG']
                    if code == "INFO-000":
                        status = "[bold green]정상 동작 (Active)[/bold green]"
                    elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in msg:
                        status = "[bold yellow]일일 한도 초과 (Exhausted)[/bold yellow]"
                    else:
                        status = f"[bold red]오류 ({code}: {msg})[/bold red]"
                else:
                    status = "[bold red]알 수 없는 응답 형식[/bold red]"
            except Exception as e:
                status = f"[bold red]통신 오류 또는 WAF 차단 ({str(e)})[/bold red]"

            logger.info(f"Key {idx+1} ({masked_key}): {status}")
            if shutdown_event.wait(0.5):
                break

        logger.info("--- 점검 완료 ---\n")
