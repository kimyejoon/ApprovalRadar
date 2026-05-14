"""
test_config.py
──────────────
Gap 분석 개선사항 #1, #2, #3에 대한 설정 값 검증
- httpx 라이브러리 설치 여부
- Jitter 범위 설정 (GAP_MIN < GAP_MAX)
- 탐색 주기 설정 (SCRAPER_INTERVAL_MINUTES)
- env 오버라이드 동작
"""
import os
import importlib
# pyrefly: ignore [missing-import]
import pytest


class TestHttpxAvailability:
    """#1 httpx 라이브러리 설치 및 사용 가능 여부"""

    def test_httpx_importable(self):
        """httpx가 임포트 가능한지 확인 (requests 대체)"""
        # pyrefly: ignore [missing-import]
        import httpx
        assert httpx is not None

    def test_httpx_version_sufficient(self):
        """httpx 버전이 0.28 이상인지 확인"""
        # pyrefly: ignore [missing-import]
        import httpx
        major, minor, *_ = httpx.__version__.split(".")
        assert (int(major), int(minor)) >= (0, 28), f"httpx 버전 부족: {httpx.__version__}"

    def test_requests_not_used_in_foodsafety_api(self):
        """foodsafety_api.py에 'import requests' 참조가 없는지 확인"""
        with open("app/clients/foodsafety_api.py") as f:
            src = f.read()
        assert "import requests" not in src, "requests가 아직 남아있음! httpx로 전환 필요"
        assert "import httpx" in src, "httpx import가 없음"

    def test_requests_not_used_in_admin(self):
        """admin.py에 'import requests' 참조가 없는지 확인"""
        with open("app/api/endpoints/admin.py") as f:
            src = f.read()
        assert "import requests" not in src, "admin.py에 requests 참조 남아있음"


class TestJitterConfig:
    """#2 Jitter(무작위 지연) 설정 검증"""

    def test_gap_min_max_exist(self):
        """GAP_MIN, GAP_MAX가 settings에 존재하는지 확인"""
        from app.core.config import settings
        assert hasattr(settings, "GAP_MIN"), "settings에 GAP_MIN 없음"
        assert hasattr(settings, "GAP_MAX"), "settings에 GAP_MAX 없음"

    def test_gap_range_valid(self):
        """GAP_MIN < GAP_MAX이고 양수인지 확인"""
        from app.core.config import settings
        assert settings.GAP_MIN > 0, "GAP_MIN이 0 이하"
        assert settings.GAP_MAX > settings.GAP_MIN, "GAP_MAX가 GAP_MIN보다 작거나 같음"

    def test_jitter_distribution_is_random(self):
        """random.uniform이 실제로 다른 값을 생성하는지 확인 (100회 중 중복이 99% 미만)"""
        import random
        from app.core.config import settings
        samples = [random.uniform(settings.GAP_MIN, settings.GAP_MAX) for _ in range(100)]
        unique_ratio = len(set(samples)) / len(samples)
        assert unique_ratio > 0.95, f"Jitter 무작위성 부족: 유니크 비율={unique_ratio:.2f}"

    def test_jitter_applied_in_industry_filler(self):
        """industry_filler.py에 random.uniform이 사용되는지 확인"""
        with open("app/services/industry_filler.py") as f:
            src = f.read()
        assert "import random" in src, "random import 없음"
        assert "random.uniform" in src, "Jitter(random.uniform) 미적용"
        assert "GAP_SECONDS" not in src, "레거시 GAP_SECONDS 직접 참조 남아있음"


class TestScraperInterval:
    """#3 탐색 주기 글로벌 상수화 검증"""

    def test_scraper_interval_exists(self):
        """SCRAPER_INTERVAL_MINUTES가 settings에 존재하는지 확인"""
        from app.core.config import settings
        assert hasattr(settings, "SCRAPER_INTERVAL_MINUTES")

    def test_scraper_interval_default_is_30(self):
        """기본값이 30분인지 확인 (단, env에 SCRAPER_INTERVAL_MINUTES가 없을 때)"""
        saved = os.environ.pop("SCRAPER_INTERVAL_MINUTES", None)
        try:
            # settings 재로드
            import app.core.config as cfg
            importlib.reload(cfg)
            assert cfg.settings.SCRAPER_INTERVAL_MINUTES == 30, \
                f"기본값이 30이 아님: {cfg.settings.SCRAPER_INTERVAL_MINUTES}"
        finally:
            if saved is not None:
                os.environ["SCRAPER_INTERVAL_MINUTES"] = saved
            importlib.reload(cfg)

    def test_scraper_interval_env_override(self):
        """SCRAPER_INTERVAL_MINUTES=5 env를 설정하면 5가 되는지 확인"""
        os.environ["SCRAPER_INTERVAL_MINUTES"] = "5"
        try:
            import app.core.config as cfg
            importlib.reload(cfg)
            assert cfg.settings.SCRAPER_INTERVAL_MINUTES == 5, \
                f"env 오버라이드 실패: {cfg.settings.SCRAPER_INTERVAL_MINUTES}"
        finally:
            del os.environ["SCRAPER_INTERVAL_MINUTES"]
            importlib.reload(cfg)

    def test_scraper_interval_invalid_env_uses_default(self):
        """SCRAPER_INTERVAL_MINUTES=abc 잘못된 값이면 기본값(30) 유지"""
        os.environ["SCRAPER_INTERVAL_MINUTES"] = "abc"
        try:
            import app.core.config as cfg
            importlib.reload(cfg)
            assert cfg.settings.SCRAPER_INTERVAL_MINUTES == 30, \
                "잘못된 env 값 시 기본값 30을 사용해야 함"
        finally:
            del os.environ["SCRAPER_INTERVAL_MINUTES"]
            importlib.reload(cfg)

    def test_hardcoded_30_not_in_scheduler(self):
        """scheduler.py에 하드코딩 minutes=30이 없는지 확인"""
        with open("app/core/scheduler.py") as f:
            src = f.read()
        assert "minutes=30" not in src or "SCRAPER_INTERVAL_MINUTES" in src, \
            "scheduler.py에 하드코딩 30이 남아있음"
        assert "SCRAPER_INTERVAL_MINUTES" in src, "settings 상수 참조 없음"
