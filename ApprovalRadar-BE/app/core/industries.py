"""
식품위생법 업종 상수 공통 정의
모든 수집 경로(diff_crawler, chng_dt_poller 등)에서 이 파일을 import하여 사용.
"""

# ── 적극 스캔 대상 업종 (I2861 Oldest-First Scan 타깃) ──────────────────────
TARGET_INDUSTRIES: frozenset[str] = frozenset({
    "일반음식점",
    "휴게음식점",
    "제과점영업",
})

# ── 식품위생법 소관이나 스캔에서 제외 (페이지 경계 인식용) ────────────────────
# I2861에는 존재하지만 Oldest-First Scan에서는 페이지 단위 스킵
SKIP_INDUSTRIES: frozenset[str] = frozenset({
    "위탁급식영업",
    "집단급식소",
    "유흥주점영업",
    "단란주점",
})

# ── DB 수집 허용 전체 업종 (식품위생법 적용 업종 합집합) ─────────────────────
# I2500 CHNG_DT Poller 등에서 비식품 업종(위생용품수입업 등) 필터링 시 사용
FOOD_SERVICE_INDUSTRIES: frozenset[str] = TARGET_INDUSTRIES | SKIP_INDUSTRIES
