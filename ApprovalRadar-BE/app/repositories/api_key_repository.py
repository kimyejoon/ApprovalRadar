from typing import List, Optional, Dict, Any
from database import get_db

class ApiKeyRepository:
    @staticmethod
    def mask_key(key: str) -> str:
        return f"{key[:5]}***{key[-3:]}" if len(key) > 8 else "***"

    def get_all_keys(self) -> List[Dict[str, Any]]:
        with get_db() as conn:
            return conn.execute(
                "SELECT id, key_value, memo, is_active, created_at FROM api_keys ORDER BY id"
            ).fetchall()

    def get_key_usages(self, today: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            return conn.execute(
                "SELECT key_masked, call_count, exhausted FROM api_key_usage WHERE usage_date = ?",
                (today,)
            ).fetchall()

    def get_key_by_value(self, key_value: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            return conn.execute(
                "SELECT id, key_value, memo, is_active, created_at FROM api_keys WHERE key_value = ?",
                (key_value,)
            ).fetchone()

    def get_key_by_id(self, key_id: int) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            return conn.execute(
                "SELECT id, key_value, memo, is_active, created_at FROM api_keys WHERE id = ?",
                (key_id,)
            ).fetchone()

    def insert_key(self, key_value: str, memo: Optional[str] = None) -> None:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO api_keys (key_value, memo, is_active) VALUES (?, ?, 1)",
                (key_value, memo)
            )
            conn.commit()

    def update_key(self, key_id: int, memo: Optional[str], is_active: Optional[int]) -> None:
        with get_db() as conn:
            conn.execute(
                "UPDATE api_keys SET memo = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (memo, is_active, key_id)
            )
            conn.commit()

    def get_usage_by_masked_and_date(self, masked: str, today: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            return conn.execute(
                "SELECT call_count, exhausted FROM api_key_usage WHERE key_masked = ? AND usage_date = ?",
                (masked, today)
            ).fetchone()

    def delete_key(self, key_id: int) -> None:
        with get_db() as conn:
            conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.commit()
