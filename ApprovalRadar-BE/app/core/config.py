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
    SERVICES = ["I2861"]

    # ─── Backfill 전용 서비스 (스캐닝 ❌, 건별 단건 조회 ⭕) ──────────────────
    # I2500: 식품 인허가 세부정보 (LCNS_NO 필터로 특정 업소의 '세부업종'만 조회)
    # → industry_filler.py에서만 사용. DiffCrawler/SERVICES와 무관.
    # → fetch_data('I2500', 1, 1000, LCNS_NO=lcns_no) 형태로 단건 조회
    BACKFILL_SERVICE_ID = "I2500"
    DATA_TYPE = "json"
    
    # Crawler Settings
    MAX_WORKERS = 2
    GAP_SECONDS = 3.0   # 하위 호환성 유지
    GAP_MIN = 0.5       # Jitter 최솟값(초) - WAF 차단 시 키 전환으로 우회
    GAP_MAX = 1.5       # Jitter 최댓값(초) - 축소하여 스캔 속도 향상
    # 탐색 최소주기 - .env의 SCRAPER_INTERVAL_MINUTES 로 오버라이드 가능 (기본값 15분)
    SCRAPER_INTERVAL_MINUTES: int = 5
    # 페이지 만료 임계 시간 (분) - .env의 STALE_THRESHOLD_MINUTES 로 오버라이드 가능 (기본값 15분)
    STALE_THRESHOLD_MINUTES: int = 15
    # API 단건 fetch 타임아웃 (초) - .env의 API_FETCH_TIMEOUT_SECONDS 로 오버라이드 가능 (기본값 200초)
    # 식품안전나라 API 서버가 최대 200초가량 응답 지연될 수 있어 넉넉하게 설정
    API_FETCH_TIMEOUT_SECONDS: int = 200
    
    # 모니터링 최적화 설정
    PIVOT_INTERVAL = 5000  # 희소 색인(Sparse Index) 피벗 간격
    STATE_FILE_PATH = "result/meta_state.json"  # 메타데이터 상태 저장 파일
    
    # Rolling Scan 설정: 매 주기 스캔할 API 페이지 총 수 (전 서비스 합계)
    # 서비스별 비례 배분됨 → compute_optimal_defaults() 참조
    # 34키 기반: Oldest-First Scan은 별도 제한 없이 만료 페이지 전부 스캔
    ROLLING_SCAN_PAGES_PER_CYCLE: int = 150

    # I2861 Oldest-First Scan 병렬 워커 수 (.env SCAN_WORKERS 로 오버라이드)
    SCAN_WORKERS: int = 4
    
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
            for i in range(1, 51):  # 최대 50개 키 지원 (env fallback)
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
                self.SCRAPER_INTERVAL_MINUTES = 5  # 잘못된 값이면 기본값(5) 유지

    # Rolling Scan pages도 env 오버라이드 가능
        rsp = os.getenv("ROLLING_SCAN_PAGES_PER_CYCLE")
        if rsp is not None:
            try:
                self.ROLLING_SCAN_PAGES_PER_CYCLE = int(rsp)
            except ValueError:
                pass

        # SCAN_WORKERS: I2861 Oldest-First Scan 병렬 워커 수 (기본 4)
        sw = os.getenv("SCAN_WORKERS")
        if sw is not None:
            try:
                self.SCAN_WORKERS = max(1, min(int(sw), 16))  # 1~16 범위 클램프
            except ValueError:
                pass

        # STALE_THRESHOLD_MINUTES: env 오버라이드 (.env에서 STALE_THRESHOLD_MINUTES=15 식으로 변경 가능)
        stm = os.getenv("STALE_THRESHOLD_MINUTES")
        if stm is not None:
            try:
                self.STALE_THRESHOLD_MINUTES = int(stm)
            except ValueError:
                self.STALE_THRESHOLD_MINUTES = 15  # 잘못된 값이면 기본값 15분 유지
        else:
            self.STALE_THRESHOLD_MINUTES = 15

        # API_FETCH_TIMEOUT_SECONDS: env 오버라이드 (.env에서 API_FETCH_TIMEOUT_SECONDS=200 식으로 변경 가능)
        aft = os.getenv("API_FETCH_TIMEOUT_SECONDS")
        if aft is not None:
            try:
                self.API_FETCH_TIMEOUT_SECONDS = max(30, int(aft))  # 최소 30초
            except ValueError:
                self.API_FETCH_TIMEOUT_SECONDS = 200


def compute_optimal_defaults(
    num_api_keys: int,
    daily_limit_per_key: int = 1000,
    services_page_counts: dict = None,
    target_rotation_hours: float = 3.0,
    avg_api_delay_sec: float = 2.5,
    tail_ping_calls_per_cycle: int = 4,
    safety_margin: float = 0.80,
) -> dict:
    """
    가용 API 자원과 비즈니스 요구사항을 기반으로 최적 기본값을 계산합니다.

    Args:
        num_api_keys: 활성 API 키 수
        daily_limit_per_key: 키당 일일 한도 (기본 1,000)
        services_page_counts: 서비스별 전체 페이지 수 {"I2861": 953, "I2859": 238}
        target_rotation_hours: 목표 1회전 시간 (시간). 짧을수록 감지 빠름, API 비용 ↑
        avg_api_delay_sec: API 호출당 평균 소요 (Jitter 포함)
        tail_ping_calls_per_cycle: 주기당 Tail Ping 호출 수 (서비스 수 × 2)
        safety_margin: API 예산 안전 마진 (0.8 = 80%만 사용)

    Returns:
        dict: 최적 설정값
            - interval_minutes: 추천 크롤링 주기 (분)
            - total_pages_per_cycle: 추천 총 롤링 페이지/주기
            - per_service: {서비스: 할당 페이지/주기}
            - daily_api_calls: 예상 일일 API 호출 수
            - rotation_hours: 실제 1회전 시간 (시간, 서비스별)
    """
    if services_page_counts is None:
        services_page_counts = {"I2861": 953, "I2859": 238}

    total_pages_all = sum(services_page_counts.values())

    # ── 1. API 예산 계산 ──
    daily_budget = int(num_api_keys * daily_limit_per_key * safety_margin)

    # ── 2. 목표 주기 역산 ──
    # 1회전 = total_pages / pages_per_cycle × interval
    # 목표: 가장 큰 서비스가 target_rotation_hours 내에 1회전
    max_pages = max(services_page_counts.values())

    # 시간 제약: 스캔 소요 < 주기
    # 듀얼 커서: 페이지 소요 = (pages/2) × avg_delay
    # 스캔 시간이 주기의 80% 이내여야 함

    # 후보 주기: 10, 15, 20, 30분
    best = None
    for interval_min in [10, 15, 20, 30]:
        cycles_per_day = (24 * 60) / interval_min

        # 주기당 사용 가능한 총 API 호출 (Tail Ping 제외)
        rolling_budget_per_cycle = (daily_budget / cycles_per_day) - tail_ping_calls_per_cycle
        if rolling_budget_per_cycle < 10:
            continue

        total_rolling_pages = int(rolling_budget_per_cycle)

        # 서비스별 비례 배분
        per_service = {}
        for svc, pages in services_page_counts.items():
            share = pages / total_pages_all
            allocated = max(10, int(total_rolling_pages * share))  # 최소 10페이지
            per_service[svc] = allocated

        # 실제 스캔 소요 시간 (듀얼 커서 → /2)
        scan_time_sec = sum(per_service.values()) * avg_api_delay_sec
        scan_time_min = scan_time_sec / 60
        if scan_time_min > interval_min * 0.85:  # 스캔이 주기의 85% 초과하면 불가
            continue

        # 1회전 시간 계산 (서비스별)
        rotation = {}
        for svc, pages in services_page_counts.items():
            half_pages = pages // 2  # 듀얼 커서
            per_cursor = per_service[svc] // 2
            if per_cursor == 0:
                per_cursor = 1
            cycles_needed = (half_pages + per_cursor - 1) // per_cursor
            rotation[svc] = (cycles_needed * interval_min) / 60  # 시간

        # 가장 큰 서비스의 1회전 시간이 목표 이내인지
        max_rotation = max(rotation.values())
        actual_daily = int(sum(per_service.values()) * cycles_per_day + tail_ping_calls_per_cycle * cycles_per_day)

        candidate = {
            "interval_minutes": interval_min,
            "total_pages_per_cycle": sum(per_service.values()),
            "per_service": per_service,
            "daily_api_calls": actual_daily,
            "daily_budget": daily_budget,
            "budget_usage_pct": round(actual_daily / daily_budget * 100, 1),
            "rotation_hours": {svc: round(h, 1) for svc, h in rotation.items()},
            "scan_time_min": round(scan_time_min, 1),
        }

        if max_rotation <= target_rotation_hours:
            # 목표 달성! 가장 긴 주기 선택 (API 절약)
            best = candidate
            break
        elif best is None or max_rotation < max(best["rotation_hours"].values()):
            best = candidate

    return best


def get_rolling_pages_for_service(service_id: str) -> int:
    """
    서비스별 데이터량 비례로 롤링 스캔 페이지 수를 반환합니다.
    settings.SERVICES에 포함된 서비스만 대상으로 비례 배분합니다.
    서비스가 1개이면 전체 예산을 할당합니다.
    """
    # 서비스가 1개면 전체 할당
    if len(settings.SERVICES) <= 1:
        return settings.ROLLING_SCAN_PAGES_PER_CYCLE

    page_counts = _get_service_page_counts()
    # SERVICES에 포함된 것만 필터
    active_counts = {k: v for k, v in page_counts.items() if k in settings.SERVICES}
    total = sum(active_counts.values())
    if total == 0:
        return settings.ROLLING_SCAN_PAGES_PER_CYCLE

    share = active_counts.get(service_id, 0) / total
    allocated = max(10, int(settings.ROLLING_SCAN_PAGES_PER_CYCLE * share))
    return allocated


def _get_service_page_counts() -> dict:
    """각 서비스의 전체 페이지 수를 DB crawler_state에서 로드합니다."""
    try:
        import sqlite3
        from database import DB_FILE
        if not os.path.exists(DB_FILE):
            return {"I2861": 953}  # fallback (I2861 only)
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT service_id, last_total_count FROM crawler_state"
        ).fetchall()
        conn.close()
        result = {}
        for row in rows:
            total = row["last_total_count"] or 0
            result[row["service_id"]] = (total + 999) // 1000
        return result if result else {"I2861": 953}
    except Exception:
        return {"I2861": 953}


settings = Settings()
