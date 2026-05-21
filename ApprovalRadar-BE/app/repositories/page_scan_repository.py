import time
from database import get_db


class PageScanRepository:
    """page_scan_history 테이블에 대한 CRUD 레포지토리."""

    def load_all(self, service_id: str) -> dict:
        """service_id의 모든 페이지 스캔 이력을 로드합니다.

        Returns:
            {
                "page_timestamps": {str(page): int(unix_ts), ...},
                "page_labels":     {str(page): str(label), ...},
                "page_industries": {str(page): str(industry), ...},
            }
        """
        page_timestamps = {}
        page_labels = {}
        page_industries = {}

        with get_db() as conn:
            rows = conn.execute(
                "SELECT page_number, label, industry, last_scanned_ts "
                "FROM page_scan_history WHERE service_id = ?",
                (service_id,)
            ).fetchall()

        for row in rows:
            p = str(row["page_number"])
            if row["last_scanned_ts"] is not None:
                page_timestamps[p] = row["last_scanned_ts"]
            if row["label"] is not None:
                page_labels[p] = row["label"]
            if row["industry"] is not None:
                page_industries[p] = row["industry"]

        return {
            "page_timestamps": page_timestamps,
            "page_labels": page_labels,
            "page_industries": page_industries,
        }

    def upsert_page(
        self,
        service_id: str,
        page_number: int,
        label: str | None = None,
        industry: str | None = None,
        last_scanned_ts: int | None = None,
    ) -> None:
        """단일 페이지의 스캔 이력을 upsert합니다.
        None 값은 기존 값을 유지합니다 (COALESCE 활용).
        """
        if last_scanned_ts is None:
            last_scanned_ts = int(time.time())

        with get_db() as conn:
            conn.execute(
                """INSERT INTO page_scan_history
                       (service_id, page_number, label, industry, last_scanned_ts)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(service_id, page_number) DO UPDATE SET
                       label           = COALESCE(excluded.label, label),
                       industry        = COALESCE(excluded.industry, industry),
                       last_scanned_ts = excluded.last_scanned_ts
                """,
                (service_id, page_number, label, industry, last_scanned_ts)
            )
            conn.commit()
