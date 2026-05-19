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


def infer_change_type_from_bf_af(chng_prvns: str, bf: str, af: str) -> tuple:
    """
    CHNG_PRVNS + BF/AF 문자열 패턴 분석 → (infer_update_type, infer_update_detail) 반환.

    판별 우선순위:
    1. "지위승계" in CHNG_PRVNS → 대표자변경
    2. BF/AF가 주소 패턴 → 변경민원-주소
    3. BF/AF가 이름 패턴 (마스킹 *) → 대표자변경 (성함변경과 일원화)
    4. 나머지 → 변경민원-상호명
    5. "초기자료등록" → 초기수집(과거변경있음)
    """
    chng_prvns = chng_prvns or ""
    bf = bf or ""
    af = af or ""

    # 0. 초기자료등록
    if "초기자료등록" in chng_prvns:
        detail = f"{bf} → {af}" if bf or af else None
        return ("초기수집(과거변경있음)", detail)

    # 1. 지위승계 → 대표자변경
    if "지위승계" in chng_prvns:
        detail = f"{bf} → {af}" if bf or af else None
        return ("대표자변경", detail)

    # 2. BF/AF 내용으로 유형 판별
    if bf or af:
        sample = af or bf  # AF 우선, 없으면 BF

        # 주소 패턴: 시/도/구/동/로/길 등 행정구역 키워드
        if _is_address_pattern(sample):
            detail = f"{bf[:30]}... → {af[:30]}..." if len(bf) > 30 or len(af) > 30 else f"{bf} → {af}"
            return ("변경민원-주소", detail)

        # 이름 패턴: 마스킹 * 포함 + 비교적 짧은 문자열
        if _is_name_pattern(sample):
            detail = f"{bf} → {af}"
            return ("대표자변경", detail)

        # 나머지 → 상호명 변경
        detail = f"{bf} → {af}"
        return ("변경민원-상호명", detail)

    # 3. BF/AF 없음 → 일반 변경민원
    return ("인허가변동", None)


def _is_address_pattern(text: str) -> bool:
    """주소 패턴 판별: 시/도/구/동/로/길 등 행정구역 키워드 포함 여부."""
    import re
    if not text:
        return False
    # 행정구역 키워드
    addr_keywords = re.compile(
        r'(특별시|광역시|특별자치도|특별자치시|'
        r'\d+동\)|읍\s|면\s|리\s|'
        r'로\s\d|길\s\d|대로\s|번길\s|'
        r'\d+호\s|\d+층)'
    )
    return bool(addr_keywords.search(text))


def _is_name_pattern(text: str) -> bool:
    """이름 패턴 판별: 마스킹 * 포함 + 짧은 문자열."""
    if not text:
        return False
    # 마스킹 패턴: 김**, 이*******, S******************** 등
    if '*' in text and len(text) <= 30:
        return True
    return False
