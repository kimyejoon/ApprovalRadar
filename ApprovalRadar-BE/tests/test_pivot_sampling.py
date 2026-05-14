"""
test_pivot_sampling.py
──────────────────────
Gap 분석 개선사항 #6에 대한 Delete 은폐 감지 검증
- _sample_check_pivots 메서드 존재 여부
- 피벗 일치 시 False 반환
- 피벗 불일치 시 True 반환 (Delete 감지)
- 빈 pivots 시 False 반환 (안전)
- API 오류 시 예외 미전파 (방어적 동작)
"""
import pytest
from unittest.mock import MagicMock, patch


def make_engine(fetch_response: dict | None = None, fetch_side_effect=None):
    """DiffCrawlerEngine의 경량 Mock 버전 생성"""
    from app.services.diff_crawler import DiffCrawlerEngine

    mock_client = MagicMock()
    if fetch_side_effect:
        mock_client.fetch_data.side_effect = fetch_side_effect
    elif fetch_response is not None:
        mock_client.fetch_data.return_value = fetch_response

    mock_state_repo = MagicMock()

    engine = DiffCrawlerEngine.__new__(DiffCrawlerEngine)
    engine.service_id = "I2859"
    engine.api_client = mock_client
    engine.state_repo = mock_state_repo
    return engine


class TestPivotSamplingExists:
    """#6 코드 구조 확인"""

    def test_sample_check_pivots_method_exists(self):
        """DiffCrawlerEngine에 _sample_check_pivots 메서드가 존재하는지"""
        from app.services.diff_crawler import DiffCrawlerEngine
        assert hasattr(DiffCrawlerEngine, "_sample_check_pivots"), \
            "_sample_check_pivots 메서드 없음"

    def test_pivot_sample_ratio_defined(self):
        """PIVOT_SAMPLE_RATIO 클래스 변수가 정의되어 있는지"""
        from app.services.diff_crawler import DiffCrawlerEngine
        assert hasattr(DiffCrawlerEngine, "PIVOT_SAMPLE_RATIO")
        assert 0 < DiffCrawlerEngine.PIVOT_SAMPLE_RATIO <= 1.0, \
            "PIVOT_SAMPLE_RATIO가 유효 범위(0~1) 밖"


class TestPivotSamplingLogic:
    """#6 _sample_check_pivots 동작 검증"""

    def test_empty_pivots_returns_false(self):
        """빈 pivots 딕셔너리는 항상 False(정상)를 반환해야 함"""
        engine = make_engine()
        result = engine._sample_check_pivots({})
        assert result is False, "빈 pivots에서 True 반환 → 오탐 가능성"

    def test_matching_pivot_returns_false(self):
        """피벗 LCNS_NO가 API 응답과 일치하면 False(정상)"""
        api_response = {
            "I2859": {"row": [{"LCNS_NO": "ABC-123"}]}
        }
        engine = make_engine(fetch_response=api_response)
        pivots = {"100": "ABC-123"}  # idx=100 → LCNS_NO="ABC-123" 저장

        result = engine._sample_check_pivots(pivots)
        assert result is False, "피벗 일치인데 True 반환 → 오탐"

    def test_mismatched_pivot_returns_true(self):
        """피벗 LCNS_NO가 API 응답과 불일치하면 True(Delete 감지)"""
        api_response = {
            "I2859": {"row": [{"LCNS_NO": "XYZ-999"}]}  # 다른 값
        }
        engine = make_engine(fetch_response=api_response)
        pivots = {"100": "ABC-123"}  # 저장값: ABC-123, 실제: XYZ-999

        result = engine._sample_check_pivots(pivots)
        assert result is True, "피벗 불일치인데 False 반환 → Delete 감지 실패"

    def test_api_error_does_not_raise(self):
        """API 조회 실패 시 예외가 전파되지 않고 False(건너뜀) 처리되어야 함"""
        engine = make_engine(fetch_side_effect=Exception("API 오류"))
        pivots = {"100": "ABC-123"}

        # 예외 없이 실행되어야 함
        result = engine._sample_check_pivots(pivots)
        assert result is False, "API 오류 시 False를 반환해야 함 (방어적 처리)"

    def test_sampling_uses_subset_of_pivots(self):
        """PIVOT_SAMPLE_RATIO 비율만큼만 API 호출이 발생하는지 확인"""
        from app.services.diff_crawler import DiffCrawlerEngine

        api_response = {"I2859": {"row": [{"LCNS_NO": "MATCH"}]}}
        engine = make_engine(fetch_response=api_response)
        # 피벗 LCNS_NO를 모두 MATCH로 세팅 (전부 일치)
        pivots = {str(i): "MATCH" for i in range(100, 200)}  # 100개

        engine._sample_check_pivots(pivots)

        call_count = engine.api_client.fetch_data.call_count
        expected_max = max(1, int(len(pivots) * DiffCrawlerEngine.PIVOT_SAMPLE_RATIO)) + 1
        assert call_count <= expected_max, \
            f"샘플링이 아닌 전체 조회 발생: {call_count}회 호출"

    def test_empty_api_row_is_skipped(self):
        """API 응답에 row가 없으면 해당 피벗은 건너뛰고 False 반환"""
        api_response = {"I2859": {"row": []}}  # 빈 row
        engine = make_engine(fetch_response=api_response)
        pivots = {"100": "ABC-123"}

        result = engine._sample_check_pivots(pivots)
        assert result is False, "빈 row에서 오탐 발생"


class TestDeleteConcealmentIntegration:
    """#6 Delete 감지 후 상태 업데이트 통합 검증"""

    def test_state_updated_on_detection(self):
        """Delete 감지 시 last_total_count가 -1 감소하는지 확인"""
        import time
        from app.services.diff_crawler import DiffCrawlerEngine
        from unittest.mock import patch as _patch

        # 불일치 API 응답 (Delete 감지)
        api_response = {"I2859": {"row": [{"LCNS_NO": "XYZ-999"}]}}
        engine = make_engine(fetch_response=api_response)

        state = {
            "last_total_count": 1000,
            "pivots": {"100": "ABC-123"},
        }
        engine.state_repo.load_state.return_value = state

        # find_true_tail이 old_tail 이하 반환 → Delete 은폐 조건
        with _patch.object(engine, "find_true_tail", return_value=999):
            engine.scan_for_updates()

        # state_repo.save_state가 호출되었고, last_total_count가 999(=1000-1)여야 함
        engine.state_repo.save_state.assert_called_once()
        saved_state = engine.state_repo.save_state.call_args[0][1]
        assert saved_state["last_total_count"] == 999, \
            f"기대값 999, 실제값 {saved_state['last_total_count']}"
