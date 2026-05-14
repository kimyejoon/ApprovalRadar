"""
test_pivot_sampling.py
──────────────────────
Gap 분석 개선사항 #6에 대한 Delete 은폐 감지 검증
- pivot_manager.sample_check 함수 존재 여부
- 피벗 일치 시 False 반환
- 피벗 불일치 시 True 반환 (Delete 감지)
- 빈 pivots 시 False 반환 (안전)
- API 오류 시 예외 미전파 (방어적 동작)

✅ [리팩토링] _sample_check_pivots가 pivot_manager.sample_check로 이관됨.
"""
# pyrefly: ignore [missing-import]
import asyncio
# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def make_engine(fetch_response: dict | None = None, fetch_side_effect=None):
    """DiffCrawlerEngine의 경량 Mock 버전 생성"""
    from app.services.diff_crawler import DiffCrawlerEngine

    mock_client = MagicMock()
    if fetch_side_effect:
        # ✅ fetch_data가 async def이므로 AsyncMock 사용
        mock_client.fetch_data = AsyncMock(side_effect=fetch_side_effect)
    elif fetch_response is not None:
        mock_client.fetch_data = AsyncMock(return_value=fetch_response)
    else:
        mock_client.fetch_data = AsyncMock(return_value={})

    mock_state_repo = MagicMock()

    engine = DiffCrawlerEngine.__new__(DiffCrawlerEngine)
    engine.service_id = "I2859"
    engine.api_client = mock_client
    engine.state_repo = mock_state_repo
    return engine


class TestPivotSamplingExists:
    """#6 코드 구조 확인"""

    def test_sample_check_pivots_method_exists(self):
        """pivot_manager 모듈에 sample_check 함수가 존재하는지"""
        from app.services import pivot_manager
        assert hasattr(pivot_manager, "sample_check"), \
            "pivot_manager.sample_check 함수 없음"

    def test_pivot_sample_ratio_defined(self):
        """PIVOT_SAMPLE_RATIO 기본값이 유효 범위(0~1)인지"""
        import inspect
        from app.services import pivot_manager
        sig = inspect.signature(pivot_manager.sample_check)
        ratio = sig.parameters["sample_ratio"].default
        assert 0 < ratio <= 1.0, \
            "sample_ratio 기본값이 유효 범위(0~1) 밖"


class TestPivotSamplingLogic:
    """#6 pivot_manager.sample_check 동작 검증 (async)"""

    @pytest.mark.asyncio
    async def test_empty_pivots_returns_false(self):
        """빈 pivots 딕셔너리는 항상 False(정상)를 반환해야 함"""
        from app.services import pivot_manager
        mock_client = MagicMock()
        mock_client.fetch_data = AsyncMock(return_value={})
        result = await pivot_manager.sample_check({}, mock_client, "I2859")
        assert result is False, "빈 pivots에서 True 반환 → 오탐 가능성"

    @pytest.mark.asyncio
    async def test_matching_pivot_returns_false(self):
        """피벗 LCNS_NO가 API 응답과 일치하면 False(정상)"""
        from app.services import pivot_manager
        api_response = {
            "I2859": {"RESULT": {"CODE": "INFO-000"}, "row": [{"LCNS_NO": "ABC-123"}]}
        }
        mock_client = MagicMock()
        mock_client.fetch_data = AsyncMock(return_value=api_response)
        pivots = {"100": {"LCNS_NO": "ABC-123", "CHNG_DT": "20250101", "BSSH_NM": "테스트업소"}}

        result = await pivot_manager.sample_check(pivots, mock_client, "I2859")
        assert result is False, "피벗 일치인데 True 반환 → 오탐"

    @pytest.mark.asyncio
    async def test_mismatched_pivot_returns_true(self):
        """피벗 LCNS_NO가 API 응답과 불일치하면 True(Delete 감지)"""
        from app.services import pivot_manager
        api_response = {
            "I2859": {"RESULT": {"CODE": "INFO-000"}, "row": [{"LCNS_NO": "XYZ-999"}]}  # 다른 값
        }
        mock_client = MagicMock()
        mock_client.fetch_data = AsyncMock(return_value=api_response)
        pivots = {"100": {"LCNS_NO": "ABC-123", "CHNG_DT": "20250101", "BSSH_NM": "서로다른업소"}}

        result = await pivot_manager.sample_check(pivots, mock_client, "I2859")
        assert result is True, "피벗 불일치인데 False 반환 → Delete 감지 실패"

    @pytest.mark.asyncio
    async def test_api_error_does_not_raise(self):
        """API 조회 실패 시 예외가 전파되지 않고 False(건너뜀) 처리되어야 함"""
        from app.services import pivot_manager
        mock_client = MagicMock()
        mock_client.fetch_data = AsyncMock(side_effect=Exception("API 오류"))
        pivots = {"100": {"LCNS_NO": "ABC-123", "CHNG_DT": "20250101", "BSSH_NM": "테스트"}}

        # 예외 없이 실행되어야 함
        result = await pivot_manager.sample_check(pivots, mock_client, "I2859")
        assert result is False, "API 오류 시 False를 반환해야 함 (방어적 처리)"

    @pytest.mark.asyncio
    async def test_sampling_uses_subset_of_pivots(self):
        """sample_ratio 비율만큼만 API 호출이 발생하는지 확인"""
        from app.services import pivot_manager
        import inspect

        api_response = {"I2859": {"RESULT": {"CODE": "INFO-000"}, "row": [{"LCNS_NO": "MATCH"}]}}
        mock_client = MagicMock()
        mock_client.fetch_data = AsyncMock(return_value=api_response)
        # 피벗 LCNS_NO를 모두 MATCH로 세팅 (전부 일치) — dict 포맷
        pivots = {str(i): {"LCNS_NO": "MATCH", "CHNG_DT": "20250101", "BSSH_NM": ""} for i in range(100, 200)}  # 100개

        sig = inspect.signature(pivot_manager.sample_check)
        sample_ratio = sig.parameters["sample_ratio"].default

        await pivot_manager.sample_check(pivots, mock_client, "I2859")

        call_count = mock_client.fetch_data.call_count
        expected_max = max(1, int(len(pivots) * sample_ratio)) + 1
        assert call_count <= expected_max, \
            f"샘플링이 아닌 전체 조회 발생: {call_count}회 호출"

    @pytest.mark.asyncio
    async def test_empty_api_row_is_skipped(self):
        """API 응답에 row가 없으면 해당 피벗은 건너뛰고 False 반환"""
        from app.services import pivot_manager
        api_response = {"I2859": {"RESULT": {"CODE": "INFO-000"}, "row": []}}  # 빈 row
        mock_client = MagicMock()
        mock_client.fetch_data = AsyncMock(return_value=api_response)
        pivots = {"100": {"LCNS_NO": "ABC-123", "CHNG_DT": "20250101", "BSSH_NM": ""}}

        result = await pivot_manager.sample_check(pivots, mock_client, "I2859")
        assert result is False, "빈 row에서 오탐 발생"


class TestDeleteConcealmentIntegration:
    """#6 Delete 감지 후 상태 업데이트 통합 검증"""

    @pytest.mark.asyncio
    async def test_state_updated_on_detection(self):
        """Delete 감지 시 last_total_count가 -1 감소하는지 확인"""
        from app.services.diff_crawler import DiffCrawlerEngine
        from unittest.mock import patch as _patch, AsyncMock

        # 불일치 API 응답 (Delete 감지)
        api_response = {"I2859": {"RESULT": {"CODE": "INFO-000"}, "row": [{"LCNS_NO": "XYZ-999"}]}}
        engine = make_engine(fetch_response=api_response)

        state = {
            "last_total_count": 1000,
            "pivots": {"100": {"LCNS_NO": "ABC-123", "CHNG_DT": "20250101", "BSSH_NM": ""}},
        }
        engine.state_repo.load_state.return_value = state

        # find_true_tail이 old_tail 이하 반환 → Delete 은폐 조건
        with _patch.object(engine, "find_true_tail", new=AsyncMock(return_value=999)):
            await engine.scan_for_updates()

        # state_repo.save_state가 호출되었고, last_total_count가 999(=1000-1)여야 함
        engine.state_repo.save_state.assert_called_once()
        saved_state = engine.state_repo.save_state.call_args[0][1]
        assert saved_state["last_total_count"] == 999, \
            f"기대값 999, 실제값 {saved_state['last_total_count']}"
