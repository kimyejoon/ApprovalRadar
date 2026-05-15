from typing import Optional, Dict, Any
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database import get_db


class MemoRepository:
    """인허가 변동건 메모 CRUD 레포지토리.
    
    license_date + business_name 조합을 기준으로 건당 1개의 메모를 관리합니다.
    DB 레벨 UNIQUE 제약(business_memos 테이블)이 중복을 방지합니다.
    """

    def get_memo(self, license_date: str, business_name: str) -> Optional[Dict[str, Any]]:
        """메모를 조회합니다. 없으면 None을 반환합니다."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM business_memos WHERE license_date = ? AND business_name = ?",
                (license_date, business_name),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_memo(self, license_date: str, business_name: str, content: str) -> Dict[str, Any]:
        """메모를 생성합니다. 이미 존재하면 sqlite3.IntegrityError가 발생합니다."""
        with get_db() as conn:
            cursor = conn.execute(
                """
                INSERT INTO business_memos (license_date, business_name, content)
                VALUES (?, ?, ?)
                """,
                (license_date, business_name, content),
            )
            conn.commit()
            new_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM business_memos WHERE id = ?", (new_id,)
            ).fetchone()
            return dict(row)

    def update_memo(self, license_date: str, business_name: str, content: str) -> Optional[Dict[str, Any]]:
        """메모를 수정합니다. 존재하지 않으면 None을 반환합니다."""
        with get_db() as conn:
            conn.execute(
                """
                UPDATE business_memos
                SET content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE license_date = ? AND business_name = ?
                """,
                (content, license_date, business_name),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM business_memos WHERE license_date = ? AND business_name = ?",
                (license_date, business_name),
            ).fetchone()
            return dict(row) if row else None

    def delete_memo(self, license_date: str, business_name: str) -> bool:
        """메모를 삭제합니다. 삭제된 행이 있으면 True, 없으면 False를 반환합니다."""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM business_memos WHERE license_date = ? AND business_name = ?",
                (license_date, business_name),
            )
            conn.commit()
            return cursor.rowcount > 0
