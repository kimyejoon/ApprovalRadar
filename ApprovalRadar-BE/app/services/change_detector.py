"""
ChangeDetector: 인허가 변동 유형 감지 모듈

scraper.py의 비대해진 변경 감지 로직을 단일 책임 원칙에 따라 분리합니다.
- 대표자변경 / 상태변경 / 명칭변경을 독립 메서드로 분리하여 단위 테스트 가능
- 복수 변경 동시 발생 시 우선순위: 대표자변경 > 상태변경 > 명칭변경
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


def parse_representatives(rep_str: str) -> List[str]:
    """
    공동 대표자 파싱 로직
    예: '김**, 이**' -> ['김**', '이**']
    """
    if not rep_str:
        return []
    parts = re.split(r'[,/&]|및', rep_str)
    return [p.strip() for p in parts if p.strip()]


@dataclass
class ChangeResult:
    """변경 감지 결과를 담는 데이터 클래스."""
    is_updated: bool = False
    infer_update_type: Optional[str] = None
    infer_update_detail: Optional[str] = None
    update_type: Optional[str] = None
    prev_business_status: Optional[str] = None
    prev_representative_name: Optional[str] = None
    prev_business_name: Optional[str] = None
    rep_history: List[dict] = field(default_factory=list)
    lic_history: List[dict] = field(default_factory=list)


class ChangeDetector:
    """
    기존 DB 레코드와 신규 API 응답을 비교하여 변경 유형을 감지합니다.

    우선순위: 대표자변경 > 상태변경 > 명칭변경
    (복수 변경이 동시에 발생해도 가장 중요한 유형 하나만 infer_update_type에 기록됩니다.)
    """

    def detect(
        self,
        db_record: dict,
        new_rep_name: str,
        new_business_status: Optional[str],
        new_business_name: str,
        now: str,
    ) -> ChangeResult:
        """
        변경 유형을 감지하여 ChangeResult를 반환합니다.

        Args:
            db_record: DB에서 조회한 기존 레코드
            new_rep_name: 신규 대표자명
            new_business_status: 신규 영업상태 (I2861 등 미제공 API는 None)
            new_business_name: 신규 업소명
            now: 현재 시각 ISO 문자열 (이력 기록용)
        """
        import json

        result = ChangeResult(
            rep_history=json.loads(db_record.get("representative_history") or "[]"),
            lic_history=json.loads(db_record.get("licensing_history") or "[]"),
        )

        prev_rep = db_record.get("representative_name", "")
        prev_status = db_record.get("business_status", "")
        prev_name = db_record.get("business_name", "")

        # ── 1. 대표자 변경 감지 ─────────────────────────────────────────
        old_reps = parse_representatives(prev_rep)
        new_reps = parse_representatives(new_rep_name)
        if new_rep_name and set(old_reps) != set(new_reps):
            result.is_updated = True
            result.update_type = "대표자변경"
            result.prev_representative_name = prev_rep
            result.rep_history.append({
                "date": now,
                "prev": prev_rep,
                "new": new_rep_name,
            })

        # ── 2. 영업 상태 변경 감지 ──────────────────────────────────────
        if new_business_status is not None and prev_status != new_business_status:
            result.is_updated = True
            if result.update_type is None:  # 대표자변경보다 낮은 우선순위
                result.update_type = "상태변경"
            result.prev_business_status = prev_status
            result.lic_history.append({
                "date": now,
                "type": "상태변경",
                "prev": prev_status,
                "new": new_business_status,
            })

        # ── 3. 업소명 변경 감지 ─────────────────────────────────────────
        if prev_name != new_business_name:
            result.is_updated = True
            if result.update_type is None:  # 가장 낮은 우선순위
                result.update_type = "명칭변경"
                result.prev_business_name = prev_name

        # ── 4. infer_update_type 결정 ────────────────────────────────────
        if result.update_type == "대표자변경":
            result.infer_update_type = "대표자변경"
            result.infer_update_detail = result.prev_representative_name
        elif result.update_type == "상태변경":
            result.infer_update_type = "상태변경"
            result.infer_update_detail = result.prev_business_status
        elif result.update_type == "명칭변경":
            result.infer_update_type = "명칭변경"
            result.infer_update_detail = result.prev_business_name

        return result
