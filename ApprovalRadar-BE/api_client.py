import os
import requests
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

class FoodSafetyAPIClient:
    def __init__(self):
        keys_env = os.getenv("API_KEY", "")
        # 콤마(,)로 구분된 다중 키 지원
        self.api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
        if not self.api_keys:
            raise ValueError("No API_KEY found in .env file.")
        self.current_key_index = 0
        self.base_url = "http://openapi.foodsafetykorea.go.kr/api"

    def get_next_key(self) -> str:
        key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    def fetch_data(self, service_id: str, start_idx: int, end_idx: int, **kwargs) -> Dict[str, Any]:
        """
        식품안전나라 API에서 데이터를 가져옵니다.
        """
        key = self.get_next_key()
        
        # URL 조합: http://openapi.foodsafetykorea.go.kr/api/인증키/서비스명/요청파일타입/시작/종료
        url = f"{self.base_url}/{key}/{service_id}/json/{start_idx}/{end_idx}"
        
        # 추가 파라미터 조합
        if kwargs:
            params_str = "&".join([f"{k}={v}" for k, v in kwargs.items() if v is not None])
            if params_str:
                url = f"{url}/{params_str}"
            
        print(f"Fetching: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if service_id in data:
                service_data = data[service_id]
                result_code = service_data.get("RESULT", {}).get("CODE")
                if result_code != "INFO-000":
                    print(f"API Result Code: {result_code}, MSG: {service_data.get('RESULT', {}).get('MSG')}")
                return service_data
            elif "RESULT" in data:
                # 결과만 바로 내려오는 경우 (ex: 오류)
                print(f"API Error Response: {data['RESULT']}")
                return {"RESULT": data["RESULT"]}
            else:
                return {"RESULT": {"CODE": "ERROR", "MSG": "Invalid Response Format"}}
                
        except requests.RequestException as e:
            print(f"Request Error for {service_id}: {e}")
            return {"RESULT": {"CODE": "ERROR", "MSG": str(e)}}
