import os
import threading

PAGE_SIZE = 1000  # API 페이지당 최대 조회 건수

# total_count 필드가 신뢰 가능한 서비스 목록
RELIABLE_TOTAL_COUNT_SERVICES: set[str] = set()

# [Legacy] 서비스별 피벗 검사 샘플 수 — Rolling Scan 도입으로 더 이상 사용되지 않음
MAX_SAMPLES_BY_SVC: dict[str, int] = {
    "I2859": 20,
    "I2861": 30,
}

# [Phase 3] Circuit Breaker 임계값
CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv('CIRCUIT_BREAKER_THRESHOLD', '10000'))

# [B] Circuit Breaker 연속 발동 경고 임계값
CIRCUIT_BREAKER_ALERT_AFTER = 3

# [C] bootstrap 동시성 제한
BOOTSTRAP_SEMAPHORE_LIMIT = 3

# [WAF Fix] 전역 Bootstrap 직렬화 Semaphore
_GLOBAL_BOOTSTRAP_SEMAPHORE = threading.Semaphore(1)
