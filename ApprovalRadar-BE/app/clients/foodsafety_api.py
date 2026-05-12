import requests
import threading
import time
from app.core.config import settings

class ApiClient:
    def __init__(self, log_callback=None):
        self.log_callback = log_callback or print
        self.api_keys = settings.API_KEYS.copy()
        self.current_key_idx = 0
        self.key_lock = threading.Lock()
        
    def get_current_key(self) -> str:
        with self.key_lock:
            return self.api_keys[self.current_key_idx]
            
    def rotate_key(self, failed_key: str):
        should_sleep = False
        with self.key_lock:
            if self.api_keys[self.current_key_idx] != failed_key:
                return
                
            next_idx = (self.current_key_idx + 1) % len(self.api_keys)
            if next_idx != self.current_key_idx:
                self.current_key_idx = next_idx
                new_key = self.api_keys[self.current_key_idx]
                self.log_callback(f"[키 회전] API 한도 초과! 새로운 키로 교체: {new_key[:5]}***")
            else:
                should_sleep = True
                
        if should_sleep:
            self.log_callback("[경고] API 키가 1개뿐입니다. 키 회전이 무의미하여 5분간 대기합니다.")
            time.sleep(300)
                
    def fetch_data(self, start_idx: int, end_idx: int, timeout: int = 10) -> dict:
        """주어진 구간의 데이터를 조회합니다. WAF 차단이나 네트워크 오류는 상위에서 처리해야 합니다."""
        api_key = self.get_current_key()
        url = f"{settings.BASE_URL}/{api_key}/{settings.SERVICE_ID}/{settings.DATA_TYPE}/{start_idx}/{end_idx}"
        return requests.get(url, timeout=timeout).json(), api_key

    def check_keys_status(self):
        """모든 로드된 API 키의 상태를 테스트하여 출력합니다."""
        self.log_callback(f"\n--- API 키 상태 점검 시작 (총 {len(self.api_keys)}개) ---")
        
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
                
            self.log_callback(f"Key {idx+1} ({masked_key}): {status}")
            time.sleep(0.5) # 과부하 방지
            
        self.log_callback("--- 점검 완료 ---\n")
