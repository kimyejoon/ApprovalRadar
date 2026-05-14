import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Food Safety OpenAPI
    BASE_URL = "http://openapi.foodsafetykorea.go.kr/api"
    SERVICE_ID = "I2859"
    # ─── 스캐닝 대상 서비스 (인허가 변동 실시간 감지) ────────────────────────
    # I2859: 식품업소 인허가변경정보 (LOCP_ADDR, BSN_STATE_NM, PRSDNT_NM)
    # I2861: 음식점업소 인허가변경정보 (SITE_ADDR, CHNG_DT - I2500과 동일 필드)
    # → DiffCrawlerEngine이 주기적으로 tail을 비교하여 신규 변동을 감지
    SERVICES = ["I2859", "I2861"]

    # ─── Backfill 전용 서비스 (스캐닝 ❌, 건별 단건 조회 ⭕) ──────────────────
    # I2500: 식품 인허가 세부정보 (LCNS_NO 필터로 특정 업소의 '세부업종'만 조회)
    # → industry_filler.py에서만 사용. DiffCrawler/SERVICES와 무관.
    # → fetch_data('I2500', 1, 1000, LCNS_NO=lcns_no) 형태로 단건 조회
    BACKFILL_SERVICE_ID = "I2500"
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
