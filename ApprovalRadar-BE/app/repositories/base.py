from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple

class AbstractBusinessRepository(ABC):
    @abstractmethod
    def get_business_by_license_no(self, license_no: str, conn: Optional[Any] = None) -> Optional[dict]:
        pass

    @abstractmethod
    def insert_business(self, record: dict, conn: Optional[Any] = None) -> None:
        pass

    @abstractmethod
    def update_business(self, license_no: str, updates: dict, conn: Optional[Any] = None) -> None:
        pass

    @abstractmethod
    def get_approvals(
        self, page: int, size: int, search: Optional[str] = None,
        start_date: Optional[str] = None, end_date: Optional[str] = None,
        regions: Optional[List[str]] = None, sort_by: str = "created_at",
        sort_order: str = "desc", infer_update_types: Optional[List[str]] = None,
        industry_types: Optional[List[str]] = None
    ) -> Tuple[List[dict], int]:
        pass


class AbstractMemoRepository(ABC):
    @abstractmethod
    def get_memo(self, license_date: str, business_name: str) -> Optional[dict]:
        pass

    @abstractmethod
    def create_memo(self, license_date: str, business_name: str, content: str) -> dict:
        pass

    @abstractmethod
    def update_memo(self, license_date: str, business_name: str, content: str) -> Optional[dict]:
        pass

    @abstractmethod
    def delete_memo(self, license_date: str, business_name: str) -> bool:
        pass
