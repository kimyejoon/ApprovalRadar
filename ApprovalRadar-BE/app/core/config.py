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
    GAP_SECONDS = 3.0   # 하위 호환성 유지
    GAP_MIN = 1.5       # Jitter 최솟값(초) - WAF/IP 차단 방지용 무작위 지연
    GAP_MAX = 4.0       # Jitter 최댓값(초)
    # 탐색 최소주기 - .env의 SCRAPER_INTERVAL_MINUTES 로 오버라이드 가능 (기본값 30분)
    SCRAPER_INTERVAL_MINUTES: int = 30
    
    # 모니터링 최적화 설정
    PIVOT_INTERVAL = 5000  # 희소 색인(Sparse Index) 피벗 간격
    STATE_FILE_PATH = "result/meta_state.json"  # 메타데이터 상태 저장 파일
    
    # API Keys
    API_KEYS = []
    
    def __init__(self):
        self._load_api_keys()
        
    def _load_api_keys(self):
        """API 키를 DB(api_keys 테이블) 우선으로 로드합니다. DB에 키가 없으면 env를 fallback으로 사용."""
        self.API_KEYS = []
        
        # 1차: DB에서 활성 키 로드
        try:
            import sqlite3
            from database import DB_FILE
            db_path = DB_FILE
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                rows = conn.execute(
                    "SELECT key_value FROM api_keys WHERE is_active = 1 ORDER BY id"
                ).fetchall()
                conn.close()
                self.API_KEYS = [row[0] for row in rows if row[0]]
        except Exception:
            pass  # DB 미초기화 상태면 env fallback으로 진행

        # 2차 fallback: env에서 로드 (DB 키가 없을 때)
        if not self.API_KEYS:
            for i in range(1, 10):
                key = os.getenv(f"FOOD_SAFETY_API_KEY_{i}")
                if key:
                    self.API_KEYS.append(key)
            
            if not self.API_KEYS:
                fallback_key = os.getenv("FOOD_SAFETY_API_KEY")
                if fallback_key:
                    self.API_KEYS.append(fallback_key)
                else:
                    raise ValueError("DB 및 환경변수에 등록된 API 키가 없습니다. api_keys 테이블 또는 FOOD_SAFETY_API_KEY_1 을 설정해주세요.")

        # SCRAPER_INTERVAL_MINUTES: env 오버라이드 (.env에서 SCRAPER_INTERVAL_MINUTES=10 식으로 변경 가능)
        interval = os.getenv("SCRAPER_INTERVAL_MINUTES")
        if interval is not None:
            try:
                self.SCRAPER_INTERVAL_MINUTES = int(interval)
            except ValueError:
                pass  # 잘못된 값이면 기본값(30) 유지

settings = Settings()
