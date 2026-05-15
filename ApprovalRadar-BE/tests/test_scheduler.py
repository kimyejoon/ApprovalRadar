"""
test_scheduler.py
─────────────────
Gap 분석 개선사항 #3, #5에 대한 스케줄러 설정 검증
- 크롤링 주기가 settings.SCRAPER_INTERVAL_MINUTES를 따르는지
- 세부업종 백필 job이 등록되는지
- 실제 APScheduler job 등록 단위 테스트

✅ [async 전환] 스케줄러 래퍼 함수(_scraper_job, _backfill_job 등)가
   asyncio.run()을 내부에서 호출하는 구조로 변경됨.
   run_all_scrapers 등은 래퍼 내부에서 지연 임포트되므로 모듈 레벨 패치 불필요.
"""
# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import patch, MagicMock


class TestSchedulerJobRegistration:
    """#3, #5 스케줄러 job 등록 검증"""

    def _run_start_scheduler(self) -> dict:
        """start_scheduler() 실행 후 등록된 job kwargs dict 반환 헬퍼."""
        # pyrefly: ignore [missing-import]
        from apscheduler.schedulers.background import BackgroundScheduler

        registered_jobs = {}

        mock_scheduler = MagicMock(spec=BackgroundScheduler)
        def capture_add_job(fn, trigger, **kwargs):
            registered_jobs[kwargs.get("id", "unknown")] = kwargs
        mock_scheduler.add_job.side_effect = capture_add_job

        with patch("app.core.scheduler.scheduler", mock_scheduler), \
             patch("database.vacuum_db", MagicMock()), \
             patch("database.backup_db", MagicMock()):
            # 모듈 캐시 우회: importlib.reload 없이 직접 함수 호출
            import importlib
            import app.core.scheduler as sched_module
            importlib.reload(sched_module)
            sched_module.scheduler = mock_scheduler
            sched_module.start_scheduler()

        return registered_jobs

    def test_scraper_job_uses_settings_interval(self):
        """scraper_job의 주기가 settings.SCRAPER_INTERVAL_MINUTES를 따르는지 확인"""
        from app.core.config import settings

        registered_jobs = {}

        # pyrefly: ignore [missing-import]
        from apscheduler.schedulers.background import BackgroundScheduler
        mock_scheduler = MagicMock(spec=BackgroundScheduler)
        def capture_add_job(fn, trigger, **kwargs):
            registered_jobs[kwargs.get("id", "unknown")] = kwargs
        mock_scheduler.add_job.side_effect = capture_add_job

        import app.core.scheduler as sched_module
        original_scheduler = sched_module.scheduler
        sched_module.scheduler = mock_scheduler
        try:
            sched_module.start_scheduler()
        finally:
            sched_module.scheduler = original_scheduler

        assert "scraper_job" in registered_jobs, "scraper_job 등록 안됨"
        actual_interval = registered_jobs["scraper_job"].get("minutes")
        assert actual_interval == settings.SCRAPER_INTERVAL_MINUTES, \
            f"주기 불일치: 실제={actual_interval}, 설정={settings.SCRAPER_INTERVAL_MINUTES}"

    def test_backfill_job_registered(self):
        """backfill_job이 스케줄러에 등록되는지 확인 (#5 자동 재시도)"""
        registered_ids = []

        # pyrefly: ignore [missing-import]
        from apscheduler.schedulers.background import BackgroundScheduler
        mock_scheduler = MagicMock(spec=BackgroundScheduler)
        def capture_add_job(fn, trigger, **kwargs):
            registered_ids.append(kwargs.get("id", "unknown"))
        mock_scheduler.add_job.side_effect = capture_add_job

        import app.core.scheduler as sched_module
        original_scheduler = sched_module.scheduler
        sched_module.scheduler = mock_scheduler
        try:
            sched_module.start_scheduler()
        finally:
            sched_module.scheduler = original_scheduler

        assert "backfill_job" in registered_ids, \
            "backfill_job 미등록 → 세부업종 자동 재시도 불가"

    def test_backfill_job_is_6hour_interval(self):
        """backfill_job이 6시간 간격으로 등록되는지 확인"""
        registered_jobs = {}

        # pyrefly: ignore [missing-import]
        from apscheduler.schedulers.background import BackgroundScheduler
        mock_scheduler = MagicMock(spec=BackgroundScheduler)
        def capture_add_job(fn, trigger, **kwargs):
            registered_jobs[kwargs.get("id", "unknown")] = kwargs
        mock_scheduler.add_job.side_effect = capture_add_job

        import app.core.scheduler as sched_module
        original_scheduler = sched_module.scheduler
        sched_module.scheduler = mock_scheduler
        try:
            sched_module.start_scheduler()
        finally:
            sched_module.scheduler = original_scheduler

        assert "backfill_job" in registered_jobs
        assert registered_jobs["backfill_job"].get("hours") == 6, \
            "backfill_job이 6시간 간격이 아님"

    def test_key_recovery_job_registered(self):
        """key_recovery_job이 10분 간격으로 등록되는지 확인 (소진 후 10분마다 재시도)"""
        registered_jobs = {}

        # pyrefly: ignore [missing-import]
        from apscheduler.schedulers.background import BackgroundScheduler
        mock_scheduler = MagicMock(spec=BackgroundScheduler)
        def capture_add_job(fn, trigger, **kwargs):
            registered_jobs[kwargs.get("id", "unknown")] = kwargs
        mock_scheduler.add_job.side_effect = capture_add_job

        import app.core.scheduler as sched_module
        original_scheduler = sched_module.scheduler
        sched_module.scheduler = mock_scheduler
        try:
            sched_module.start_scheduler()
        finally:
            sched_module.scheduler = original_scheduler

        assert "key_recovery_job" in registered_jobs, "key_recovery_job 미등록"
        assert registered_jobs["key_recovery_job"].get("minutes") == 10, \
            "key_recovery_job이 10분 간격이 아님 (소진 후 10분 재시도 요구사항)"
