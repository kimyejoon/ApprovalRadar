"""
BusinessRepository 통합 테스트.

인메모리 SQLite DB를 사용하여 실제 DB 파일 오염 없이 실행됩니다.
database.py의 _thread_local을 패치하여 테스트 전용 연결을 주입합니다.
"""
import json
import sqlite3
import sys
import os
import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── 픽스처: 인메모리 DB + 테이블 생성 ────────────────────────────────────────

@pytest.fixture()
def in_memory_db(monkeypatch):
    """
    인메모리 SQLite 커넥션을 생성하고 database._thread_local.conn을 패치합니다.
    테스트 종료 후 자동으로 정리됩니다.
    """
    import database as db_module

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # 필요한 테이블 생성
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS businesses (
            license_no TEXT PRIMARY KEY,
            business_name TEXT,
            address TEXT,
            representative_name TEXT,
            business_status TEXT,
            license_date TEXT,
            phone_number TEXT,
            industry_type TEXT,
            representative_history TEXT DEFAULT '[]',
            licensing_history TEXT DEFAULT '[]',
            last_event_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 1,
            update_type TEXT,
            prev_business_status TEXT,
            prev_representative_name TEXT,
            prev_business_name TEXT,
            infer_update_type TEXT,
            infer_update_detail TEXT,
            last_event_time TEXT,
            license_time TEXT,
            change_reason TEXT,
            change_before TEXT,
            change_after TEXT,
            collected_by TEXT,
            is_read INTEGER DEFAULT 0,
            read_at TEXT
        );
    """)
    conn.commit()

    # _thread_local.conn을 인메모리 커넥션으로 교체
    monkeypatch.setattr(db_module._thread_local, "conn", conn, raising=False)

    yield conn

    conn.close()
    monkeypatch.setattr(db_module._thread_local, "conn", None, raising=False)


def _sample_record(**overrides):
    base = {
        "license_no": "LN-001",
        "business_name": "테스트식당",
        "address": "서울 강남구",
        "representative_name": "홍길동",
        "business_status": "영업중",
        "license_date": "20230101",
        "phone_number": "010-1234-5678",
        "industry_type": "일반음식점",
        "last_event_date": "20230601",
        "infer_update_type": "신규등록",
        "infer_update_detail": None,
        "last_event_time": None,
        "license_time": None,
    }
    base.update(overrides)
    return base


# ─── insert_business 테스트 ────────────────────────────────────────────────────

class TestInsertBusiness:
    def test_insert_creates_record(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record())

        result = repo.get_business_by_license_no("LN-001")
        assert result is not None
        assert result["business_name"] == "테스트식당"
        assert result["representative_name"] == "홍길동"

    def test_insert_sets_is_new_flag(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record())

        result = repo.get_business_by_license_no("LN-001")
        assert result["is_new"] == 1

    def test_insert_missing_optional_fields(self, in_memory_db):
        """optional 필드가 없어도 삽입이 성공해야 합니다."""
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        record = _sample_record(industry_type=None, phone_number=None)
        repo.insert_business(record)

        result = repo.get_business_by_license_no("LN-001")
        assert result is not None


# ─── update_business 테스트 ───────────────────────────────────────────────────

class TestUpdateBusiness:
    def test_update_representative_name(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record())

        updates = {
            "business_name": "테스트식당",
            "address": "서울 강남구",
            "representative_name": "김철수",
            "business_status": "영업중",
            "phone_number": "010-0000-0000",
            "industry_type": "일반음식점",
            "representative_history": json.dumps([{"date": "now", "prev": "홍길동", "new": "김철수"}]),
            "licensing_history": "[]",
            "update_type": "대표자변경",
            "prev_business_status": None,
            "prev_representative_name": "홍길동",
            "prev_business_name": None,
            "infer_update_type": "대표자변경",
            "infer_update_detail": "홍길동",
            "last_event_date": "20230701",
            "last_event_time": None,
            "license_time": None,
            "updated_at": "2023-07-01T00:00:00",
        }
        repo.update_business("LN-001", updates)

        result = repo.get_business_by_license_no("LN-001")
        assert result["representative_name"] == "김철수"
        assert result["infer_update_type"] == "대표자변경"

    def test_update_industry_type_not_overwritten_by_null(self, in_memory_db):
        """industry_type이 이미 있는데 None으로 업데이트 시 기존값 유지 (COALESCE)."""
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record(industry_type="일반음식점"))

        updates = {
            "business_name": "테스트식당",
            "address": "서울 강남구",
            "representative_name": "홍길동",
            "business_status": "영업중",
            "phone_number": "010-1234-5678",
            "industry_type": None,  # None → COALESCE로 기존값 유지
            "representative_history": "[]",
            "licensing_history": "[]",
            "update_type": None,
            "prev_business_status": None,
            "prev_representative_name": None,
            "prev_business_name": None,
            "infer_update_type": None,
            "infer_update_detail": None,
            "last_event_date": "20230701",
            "last_event_time": None,
            "license_time": None,
            "updated_at": "2023-07-01T00:00:00",
        }
        repo.update_business("LN-001", updates)

        result = repo.get_business_by_license_no("LN-001")
        assert result["industry_type"] == "일반음식점"


# ─── update_read_info 테스트 ──────────────────────────────────────────────────

class TestUpdateReadInfo:
    def test_mark_as_read(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record())

        result_before = repo.get_business_by_license_no("LN-001")
        assert result_before["is_read"] == 0

        repo.update_read_info("LN-001")

        result_after = repo.get_business_by_license_no("LN-001")
        assert result_after["is_read"] == 1
        assert result_after["read_at"] is not None


# ─── update_industry_type 테스트 ─────────────────────────────────────────────

class TestUpdateIndustryType:
    def test_update_industry_type(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record(industry_type=None))

        repo.update_industry_type("LN-001", "제과점영업")

        result = repo.get_business_by_license_no("LN-001")
        assert result["industry_type"] == "제과점영업"


# ─── get_approvals 페이지네이션 테스트 ───────────────────────────────────────

class TestGetApprovals:
    def test_pagination(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        for i in range(5):
            repo.insert_business(_sample_record(
                license_no=f"LN-{i:03d}",
                business_name=f"식당{i}",
                last_event_date="20230601",
            ))

        result, total = repo.get_approvals(
            page=1, size=3, search=None, start_date=None,
            end_date=None, regions=None, sort_by="created_at", sort_order="desc"
        )
        assert total == 5
        assert len(result) == 3

    def test_search_filter(self, in_memory_db):
        from app.repositories.business_repository import BusinessRepository
        repo = BusinessRepository()
        repo.insert_business(_sample_record(license_no="LN-001", business_name="김밥천국"))
        repo.insert_business(_sample_record(license_no="LN-002", business_name="피자헛"))

        result, total = repo.get_approvals(
            page=1, size=10, search="김밥", start_date=None,
            end_date=None, regions=None, sort_by="created_at", sort_order="desc"
        )
        assert total == 1
        assert result[0]["business_name"] == "김밥천국"
