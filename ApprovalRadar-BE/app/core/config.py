import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Food Safety OpenAPI
    BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
    SERVICE_ID = "I2859"
    DATA_TYPE = "json"
    
    # Crawler Settings
    MAX_WORKERS = 2
    GAP_SECONDS = 3.0
    
    # 모니터링 최적화 설정
    PIVOT_INTERVAL = 5000  # 희소 색인(Sparse Index) 피벗 간격
    STATE_FILE_PATH = "result/meta_state.json"  # 메타데이터 상태 저장 파일
    
    # API Keys
    API_KEYS = []
    
    def __init__(self):
        self._load_api_keys()
        
    def _load_api_keys(self):
        self.API_KEYS = []
        for i in range(1, 10):
            key = os.getenv(f"FOOD_SAFETY_API_KEY_{i}")
            if key:
                self.API_KEYS.append(key)
        
        if not self.API_KEYS:
            fallback_key = os.getenv("FOOD_SAFETY_API_KEY")
            if fallback_key:
                self.API_KEYS.append(fallback_key)
            else:
                raise ValueError("환경변수에 등록된 API 키가 없습니다. FOOD_SAFETY_API_KEY_1 을 설정해주세요.")

settings = Settings()
