"""
ChangeDetector 단위 테스트.

DB나 API 의존성 없이 순수 로직만 테스트합니다.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.change_detector import ChangeDetector, parse_representatives


NOW = "2023-07-01T00:00:00"


def _make_db_record(**overrides):
    base = {
        "representative_name": "홍길동",
        "business_status": "영업중",
        "business_name": "테스트식당",
        "representative_history": "[]",
        "licensing_history": "[]",
    }
    base.update(overrides)
    return base


# ─── parse_representatives 테스트 ─────────────────────────────────────────────

class TestParseRepresentatives:
    def test_single(self):
        assert parse_representatives("홍길동") == ["홍길동"]

    def test_comma_separated(self):
        result = parse_representatives("홍길동, 김철수")
        assert set(result) == {"홍길동", "김철수"}

    def test_slash_separated(self):
        result = parse_representatives("홍길동/김철수")
        assert set(result) == {"홍길동", "김철수"}

    def test_empty_string(self):
        assert parse_representatives("") == []

    def test_none(self):
        assert parse_representatives(None) == []


# ─── ChangeDetector 테스트 ────────────────────────────────────────────────────

class TestChangeDetector:
    def setup_method(self):
        self.detector = ChangeDetector()

    def test_no_change(self):
        """변경 없음: is_updated=False"""
        db = _make_db_record()
        result = self.detector.detect(
            db_record=db,
            new_rep_name="홍길동",
            new_business_status="영업중",
            new_business_name="테스트식당",
            now=NOW,
        )
        assert result.is_updated is False
        assert result.infer_update_type is None

    # ── 대표자 변경 ─────────────────────────────────────────────────────────

    def test_representative_change(self):
        db = _make_db_record(representative_name="홍길동")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="김철수",
            new_business_status="영업중",
            new_business_name="테스트식당",
            now=NOW,
        )
        assert result.is_updated is True
        assert result.infer_update_type == "대표자변경"
        assert result.prev_representative_name == "홍길동"
        assert len(result.rep_history) == 1
        assert result.rep_history[0]["prev"] == "홍길동"
        assert result.rep_history[0]["new"] == "김철수"

    def test_representative_order_ignored(self):
        """공동 대표자 순서가 바뀌어도 변경으로 감지하지 않아야 함."""
        db = _make_db_record(representative_name="홍길동, 김철수")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="김철수, 홍길동",
            new_business_status="영업중",
            new_business_name="테스트식당",
            now=NOW,
        )
        assert result.is_updated is False

    # ── 상태 변경 ───────────────────────────────────────────────────────────

    def test_status_change(self):
        db = _make_db_record(business_status="영업중")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="홍길동",
            new_business_status="폐업",
            new_business_name="테스트식당",
            now=NOW,
        )
        assert result.is_updated is True
        assert result.infer_update_type == "상태변경"
        assert result.prev_business_status == "영업중"
        assert len(result.lic_history) == 1

    def test_status_none_not_detected(self):
        """I2861처럼 상태 미제공(None)이면 변경 감지 안 함."""
        db = _make_db_record(business_status="영업중")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="홍길동",
            new_business_status=None,  # 미제공
            new_business_name="테스트식당",
            now=NOW,
        )
        assert result.infer_update_type != "상태변경"

    # ── 명칭 변경 ───────────────────────────────────────────────────────────

    def test_name_change(self):
        db = _make_db_record(business_name="테스트식당")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="홍길동",
            new_business_status="영업중",
            new_business_name="새이름식당",
            now=NOW,
        )
        assert result.is_updated is True
        assert result.infer_update_type == "명칭변경"
        assert result.prev_business_name == "테스트식당"

    # ── 우선순위 테스트 ─────────────────────────────────────────────────────

    def test_priority_representative_over_status(self):
        """대표자변경 + 상태변경 동시 → infer_update_type은 대표자변경."""
        db = _make_db_record(representative_name="홍길동", business_status="영업중")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="김철수",
            new_business_status="폐업",
            new_business_name="테스트식당",
            now=NOW,
        )
        assert result.is_updated is True
        assert result.infer_update_type == "대표자변경"
        # 상태 변경 이력도 기록되어야 함
        assert len(result.lic_history) == 1

    def test_priority_status_over_name(self):
        """상태변경 + 명칭변경 동시 → infer_update_type은 상태변경."""
        db = _make_db_record(business_status="영업중", business_name="테스트식당")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="홍길동",
            new_business_status="폐업",
            new_business_name="새이름식당",
            now=NOW,
        )
        assert result.is_updated is True
        assert result.infer_update_type == "상태변경"

    def test_priority_representative_over_name(self):
        """대표자변경 + 명칭변경 동시 → infer_update_type은 대표자변경."""
        db = _make_db_record(representative_name="홍길동", business_name="테스트식당")
        result = self.detector.detect(
            db_record=db,
            new_rep_name="김철수",
            new_business_status="영업중",
            new_business_name="새이름식당",
            now=NOW,
        )
        assert result.is_updated is True
        assert result.infer_update_type == "대표자변경"

    # ── 이력 누적 테스트 ────────────────────────────────────────────────────

    def test_history_accumulates(self):
        """기존 이력이 있으면 새 이력이 append되어야 함."""
        import json
        existing_history = [{"date": "2023-01-01", "prev": "이전대표", "new": "홍길동"}]
        db = _make_db_record(
            representative_name="홍길동",
            representative_history=json.dumps(existing_history),
        )
        result = self.detector.detect(
            db_record=db,
            new_rep_name="김철수",
            new_business_status="영업중",
            new_business_name="테스트식당",
            now=NOW,
        )
        assert len(result.rep_history) == 2
        assert result.rep_history[0]["new"] == "홍길동"
        assert result.rep_history[1]["new"] == "김철수"
