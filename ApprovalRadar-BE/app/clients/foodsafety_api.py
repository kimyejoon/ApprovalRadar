import requests
import threading
import time
from app.core.config import settings
from app.core.logger import logger

class ApiKeysExhaustedError(Exception):
    """모든 API 키가 소진되었을 때 발생하는 예외"""
    pass

class ApiClient:
    def __init__(self):
        self.api_keys = settings.API_KEYS.copy()
        self.current_key_idx = 0
        self.key_lock = threading.Lock()
        self.exhausted_keys = set()
        
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
                
    def fetch_data(self, start_idx: int, end_idx: int, max_retries: int = 5) -> dict:
        """
        주어진 구간의 데이터를 조회합니다.
        - 한도 초과(INFO-300 등) 시 자동으로 키를 회전하고 재시도합니다.
        - 서버 에러(ERROR-500 등)나 네트워크 에러 발생 시 지수 백오프(Exponential Backoff)를 적용하여 재시도합니다.
        """
        attempt = 0
        backoff = 1
        
        while attempt < max_retries:
            api_key = self.get_current_key()
            url = f"{settings.BASE_URL}/{api_key}/{settings.SERVICE_ID}/{settings.DATA_TYPE}/{start_idx}/{end_idx}"
            
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                res = response.json()
                
                if settings.SERVICE_ID in res:
                    code = res[settings.SERVICE_ID]['RESULT']['CODE']
                    msg = res[settings.SERVICE_ID]['RESULT']['MSG']
                    
                    if code == "INFO-000" or code == "INFO-200":
                        return res
                    elif code in ["INFO-300", "INFO-333"] or "유효 호출건수" in msg:
                        # 한도 초과: 키 회전 후 즉시 재시도 (백오프 적용 X)
                        self.rotate_key(api_key)
                        continue
                    elif code in ["ERROR-500", "ERROR-601"]:
                        # 서버 일시적 오류: 지수 백오프 적용
                        logger.warning(f"[API 서버 오류] {code}: {msg}. {backoff}초 후 재시도합니다...")
                        time.sleep(backoff)
                        backoff *= 2
                        attempt += 1
                        continue
                    else:
                        # 기타 치명적인 오류 (ERROR-300, ERROR-331 등)는 재시도하지 않고 예외 발생
                        logger.error(f"[API 파라미터/기타 오류] {code}: {msg}")
                        return res
                else:
                    logger.warning(f"알 수 없는 응답 형식입니다. {backoff}초 후 재시도합니다...")
                    time.sleep(backoff)
                    backoff *= 2
                    attempt += 1
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"[네트워크 오류] {str(e)}. {backoff}초 후 재시도합니다...")
                time.sleep(backoff)
                backoff *= 2
                attempt += 1
                
        logger.error(f"최대 재시도 횟수({max_retries}) 초과. API 요청 실패: {start_idx}~{end_idx}")
        return {}

    def check_keys_status(self):
        """모든 로드된 API 키의 상태를 테스트하여 출력합니다."""
        logger.info(f"\n--- API 키 상태 점검 시작 (총 {len(self.api_keys)}개) ---")
        
        for idx, key in enumerate(self.api_keys):
            masked_key = f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"
            url = f"{settings.BASE_URL}/{key}/{settings.SERVICE_ID}/{settings.DATA_TYPE}/1/1"
            
            try:
                res = requests.get(url, timeout=5).json()
                if settings.SERVICE_ID in res:
                    code = res[settings.SERVICE_ID]['RESULT']['CODE']
                    msg = res[settings.SERVICE_ID]['RESULT']['MSG']
                    
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
            time.sleep(0.5)
            
        logger.info("--- 점검 완료 ---\n")
