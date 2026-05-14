import requests
import threading
import time
from app.core.config import settings
from app.core.logger import logger
from app.core.events import shutdown_event

class ApiKeysExhaustedError(Exception):
    """모든 API 키가 소진되었을 때 발생하는 예외"""
    pass

class ApiClient:
    def __init__(self):
        self.api_keys = settings.API_KEYS.copy()
        self.current_key_idx = 0
        self.key_lock = threading.Lock()       # 키 인덱스 교체용 Lock
        self.exhausted_keys = set()
        # WAF 동시 접근 방지: 키별 요청 직렬화 Lock
        # 동일 키로 동시에 2개 이상 요청하면 "현재 접속 중인 인증키입니다" WAF 차단 발생
        self._key_locks: dict[str, threading.Lock] = {
            key: threading.Lock() for key in self.api_keys
        }

    def get_current_key(self) -> str:
        with self.key_lock:
            return self.api_keys[self.current_key_idx]
            
    def rotate_key(self, failed_key: str):
        with self.key_lock:
            # 실패한 키를 소진 목록에 추가
            self.exhausted_keys.add(failed_key)
            
            # 모든 키가 소진되었는지 확인
            if len(self.exhausted_keys) >= len(self.api_keys):
                logger.error("🚨 [긴급] 오늘자 식품나라 API 키가 모두 소진되었습니다. 크롤링이 중단됩니다.")
                raise ApiKeysExhaustedError("All API keys are exhausted for today.")
                
            if self.api_keys[self.current_key_idx] != failed_key:
                return
                
            next_idx = (self.current_key_idx + 1) % len(self.api_keys)
            self.current_key_idx = next_idx
            new_key = self.api_keys[self.current_key_idx]
            logger.info(f"[키 회전] API 한도 초과! 새로운 키로 교체: {new_key[:5]}***")

    def switch_key(self, current_key: str):
        """한도 초과가 아닌 일시적 문제(타임아웃, 임시차단)로 키를 소진시키지 않고 다음 키로 단순 변경합니다."""
        with self.key_lock:
            if self.api_keys[self.current_key_idx] != current_key:
                return
            next_idx = (self.current_key_idx + 1) % len(self.api_keys)
            self.current_key_idx = next_idx
            new_key = self.api_keys[self.current_key_idx]
            logger.info(f"[키 전환] 일시적 오류(WAF/Timeout)로 임시 키 전환: {new_key[:5]}***")
                
    def fetch_data(self, service_id: str, start_idx: int, end_idx: int, max_retries: int = 5, timeout: int = 30, **kwargs) -> dict:
        """
        주어진 구간의 데이터를 조회합니다.
        - 한도 초과(INFO-300 등) 시 자동으로 키를 회전하고 재시도합니다.
        - 서버 에러(ERROR-500 등)나 네트워크 에러 발생 시 지수 백오프(Exponential Backoff)를 적용하여 재시도합니다.
        """
        attempt = 0
        backoff = 1
        
        while attempt < max_retries and not shutdown_event.is_set():
            api_key = self.get_current_key()
            url = f"{settings.BASE_URL}/{api_key}/{service_id}/{settings.DATA_TYPE}/{start_idx}/{end_idx}"
            
            if kwargs:
                params = "&".join(f"{k}={v}" for k, v in kwargs.items())
                url += f"/{params}"
            
            # 동일 키 동시 요청 → WAF "현재 접속 중인 인증키입니다" 차단 방지
            # 같은 키를 쓰는 스레드는 순서대로 직렬화. 다른 키는 독립적으로 병렬 진행 가능.
            key_lock = self._key_locks.setdefault(api_key, threading.Lock())

            with key_lock:
                # Lock 대기 중 다른 스레드가 키를 교체했을 수 있으므로 재확인
                if self.get_current_key() != api_key:
                    continue  # 키가 바뀌었으면 새 키로 다시 루프 (attempt 소모 없음)

                try:
                    response = requests.get(url, timeout=timeout)
                    response.raise_for_status()
                    res = response.json()
                    
                    if service_id in res:
                        code = res[service_id]['RESULT']['CODE']
                        msg = res[service_id]['RESULT']['MSG']
                        
                        if code == "INFO-000" or code == "INFO-200":
                            return res
                        elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in msg:
                            self.rotate_key(api_key)
                            logger.warning(f"키 회전 후 {settings.GAP_SECONDS}초 대기...")
                            if shutdown_event.wait(settings.GAP_SECONDS):
                                logger.info("서버 종료 신호 수신. API 호출 중단.")
                                return {}
                            continue
                        elif code in ["ERROR-500", "ERROR-601"]:
                            logger.warning(f"[API 서버 오류] {code}: {msg}. {backoff}초 후 재시도합니다...")
                            if shutdown_event.wait(backoff):
                                logger.info("서버 종료 신호 수신. API 호출 중단.")
                                return {}
                            backoff *= 2
                            attempt += 1
                            continue
                        else:
                            logger.error(f"[API 파라미터/기타 오류] {code}: {msg}")
                            return res
                    else:
                        logger.warning(f"알 수 없는 응답 형식입니다. {backoff}초 후 재시도합니다...")
                        if shutdown_event.wait(backoff):
                            return {}

                except ValueError as e:
                    ctx = f"서비스:{service_id}, 추가:{kwargs}" if kwargs else f"서비스:{service_id}"
                    raw_text = response.text[:200].replace('\n', ' ') if 'response' in locals() else "N/A"
                    logger.warning(f"[API 파싱 오류] {ctx} | 서버가 JSON이 아닌 데이터를 반환했습니다 (WAF 차단 의심). 응답 미리보기: {raw_text} | 사유: {str(e)}")
                    
                    if "현재 접속 중인 인증키입니다" in raw_text:
                        logger.warning("WAF 임시 차단 감지! 키를 즉시 전환합니다.")
                        self.switch_key(api_key)
                    elif attempt >= 2:
                        logger.warning("연속적인 응답 오류 발생! 해당 키가 WAF에 의해 임시 차단된 것으로 의심되어 키를 회전합니다.")
                        self.rotate_key(api_key)
                        if shutdown_event.wait(settings.GAP_SECONDS):
                            return {}
                    else:
                        if shutdown_event.wait(backoff):
                            return {}
                    backoff *= 2
                    attempt += 1

                except requests.exceptions.Timeout as e:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    logger.warning(f"[읽기 타임아웃] {ctx} | 서버 응답 지연 ({timeout}초 초과). {backoff}초 후 재시도합니다.")
                    if shutdown_event.wait(backoff):
                        return {}
                    backoff = min(backoff * 2, 10)  # 최대 10초 대기
                    attempt += 1

                except requests.exceptions.RequestException as e:
                    ctx = f"서비스:{service_id}, 범위:{start_idx}~{end_idx}"
                    if kwargs:
                        ctx += f", 추가:{kwargs}"
                    logger.warning(f"[네트워크 통신 오류] {ctx} | 사유: {str(e)}. 연결 오류로 인해 키를 전환합니다.")
                    self.switch_key(api_key)
                    if shutdown_event.wait(backoff):
                        return {}
                    backoff *= 2
                    attempt += 1
                
        logger.error(f"❌ 최대 재시도 횟수({max_retries}) 초과. API 요청 완전 실패: {start_idx}~{end_idx}")
        raise Exception(f"식품나라 API 서버 통신 실패 (최대 재시도 초과): {start_idx}~{end_idx}")

    def check_keys_status(self, service_id: str = "I2859"):
        """모든 로드된 API 키의 상태를 테스트하여 출력합니다."""
        logger.info(f"\n--- API 키 상태 점검 시작 (총 {len(self.api_keys)}개) ---")
        
        for idx, key in enumerate(self.api_keys):
            masked_key = f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"
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
