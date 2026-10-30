"""진료 역량 규칙 엔진(C). 병원의 진료 역량 조건(PRD_v0.1.md F-13)을 만족하지 않는 병원을 후보에서 뺀다.

가용병상 조건(응급실, 중환자실), 중증응급질환 수용가능 조건, 필수 진료과 조건, 특수 자원 조건을 적용한다.
분만 자원은 병원을 거르지 않고 "분만 가능" 태그로 표시한다.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from aimp.common.settings import settings
from aimp.domain.hospital import AcceptanceStatus, Hospital
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Department, PatientCategory, Resource, SevereDiseaseCode, WarningCode

# 중환자실 가용병상 조건을 적용하는 중증 적용 규칙
SEVERE_CATEGORIES: frozenset[PatientCategory] = frozenset(
    {
        PatientCategory.SEVERE_TRAUMA,
        PatientCategory.SEVERE_NON_TRAUMA,
        PatientCategory.STROKE_SUSPECTED,
        PatientCategory.STROKE_SCREENING_POSITIVE,
    }
)

# mkioskty2(뇌경색 재관류), mkioskty3(거미막하출혈 수술), mkioskty4(기타 뇌출혈 수술)
_STROKE_TREATMENT_CODES = (SevereDiseaseCode.MKIOSKTY2, SevereDiseaseCode.MKIOSKTY3, SevereDiseaseCode.MKIOSKTY4)

# 특수 자원 → 병원이 그 자원을 갖췄는지 판정하는 조건. PRD_v0.1.md F-02 판정 규칙 표의 병원 데이터 열과 같아야 한다.
# 분만은 병원을 거르지 않고 태그로 표시하므로 이 표에 넣지 않는다(_can_deliver).
_RESOURCE_CONDITIONS: dict[Resource, Callable[[Hospital], bool]] = {
    # 셋 중 하나라도 Y
    Resource.STROKE_TREATMENT: lambda hospital: any(_accepts_disease(hospital, c) for c in _STROKE_TREATMENT_CODES),
    # mkioskty1(심근경색 재관류)이 Y
    Resource.MI_REPERFUSION: lambda hospital: _accepts_disease(hospital, SevereDiseaseCode.MKIOSKTY1),
    # API가 소아 응급실 병상(hv28)을 주지 않아 진료과 보유로 판정한다
    Resource.PEDIATRIC_EMERGENCY: lambda hospital: Department.PEDIATRICS in hospital.departments,
}


@dataclass(frozen=True)
class CandidateHospital:
    """진료 역량 조건을 통과한 후보 병원 하나."""

    hospital: Hospital
    # "병상 정보 오래됨" 태그. True면 병상 값(er_beds, icu_beds)이 지금과 다를 수 있다. 병상 값은 바꾸지 않고 그대로 둔다
    stale_beds: bool
    # "분만 가능" 태그. 환자에게 분만 자원이 필요하고 병원이 분만이 가능하면 True다. 병원을 거르는 데 쓰지 않는다
    can_deliver: bool = False


def filter_candidates(
    hospitals: Iterable[Hospital],
    severe_judgment: SevereJudgment,
    assessment: PatientAssessment | None,
    category: PatientCategory,
    queried_at: datetime,
) -> tuple[list[CandidateHospital], list[WarningCode]]:
    """(남은 후보 병원 목록, 경고 목록). 남은 후보는 입력 순서를 유지한다.

    queried_at은 병원정보 조회 시각이다. beds_updated_at(API의 lastUpdatedAt)과 같이 시간대 정보 없는 KST로 준다.
    assessment가 None이면(환자 상태 판단 실패) 중증응급질환 수용가능 조건과 필수 진료과 조건을 적용하지 않는다.
    특수 자원 조건과 "분만 가능" 태그는 severe_judgment.required_resources로 정하므로 assessment가 None이어도 적용한다.
    """
    # 심폐정지 환자에게는 어떤 조건도 적용하지 않고 "분만 가능" 태그도 붙이지 않는다. A0은 15세 미만이거나 임산부인
    # 심정지 환자에게도 소아 응급 진료나 분만 자원을 붙이므로, required_resources가 아니라 적용 규칙을 보고 건너뛴다
    if category == PatientCategory.CARDIAC_ARREST:
        return [CandidateHospital(hospital, stale_beds=False) for hospital in hospitals], []

    max_age = timedelta(minutes=settings.bed_data_max_age_minutes)
    check_icu = settings.require_icu_beds and category in SEVERE_CATEGORIES
    disease_code = assessment.severe_disease_code if assessment is not None else None
    required_depts = assessment.required_depts if assessment is not None else ()
    resources = severe_judgment.required_resources
    resource_conditions = [condition for resource, condition in _RESOURCE_CONDITIONS.items() if resource in resources]
    needs_delivery = Resource.DELIVERY in resources
    candidates: list[CandidateHospital] = []
    for hospital in hospitals:
        # 중증응급질환 수용가능 조건, 필수 진료과 조건, 특수 자원 조건은 병상 신선도 태그와 관계없이 적용한다
        if disease_code is not None and not _accepts_disease(hospital, disease_code):
            continue
        if not hospital.departments.issuperset(required_depts):  # 필수 진료과 중 하나라도 없는 병원은 뺀다
            continue
        if not all(condition(hospital) for condition in resource_conditions):  # 특수 자원 중 하나라도 없는 병원은 뺀다
            continue
        stale = hospital.beds_updated_at is None or queried_at - hospital.beds_updated_at > max_age
        # 태그가 붙은 병원에는 가용병상 조건을 적용하지 않는다
        if not stale and (not _has_er_beds(hospital) or (check_icu and not _has_icu_beds(hospital))):
            continue
        can_deliver = needs_delivery and _can_deliver(hospital)
        candidates.append(CandidateHospital(hospital, stale_beds=stale, can_deliver=can_deliver))

    warnings = [WarningCode.STALE_BED_DATA] if any(candidate.stale_beds for candidate in candidates) else []
    return candidates, warnings


def _accepts_disease(hospital: Hospital, code: SevereDiseaseCode) -> bool:
    """중증응급질환 수용가능 값이 Y면 True. 불가능·정보미제공이거나 항목이 없으면 False(PRD F-13의 조건이 "수용가능 = Y"다)."""
    acceptance = hospital.disease_acceptance.get(code)
    return acceptance is not None and acceptance.status == AcceptanceStatus.AVAILABLE


def _can_deliver(hospital: Hospital) -> bool:
    """mkioskty16(분만) 수용가능 값이 Y이거나 분만실이 가용이면 True. PRD_v0.1.md F-02 판정 규칙 표의 분만 행."""
    return _accepts_disease(hospital, SevereDiseaseCode.MKIOSKTY16) or hospital.delivery_room is True


def _has_er_beds(hospital: Hospital) -> bool:
    """응급실 가용병상이 1 이상이거나 API가 값을 주지 않았으면 True."""
    available = hospital.er_beds.available
    return available is None or available > 0


def _has_icu_beds(hospital: Hospital) -> bool:
    """중환자실 병상 종류 중 하나라도 가용병상이 1 이상이거나, API가 모든 종류의 값을 주지 않았으면 True."""
    counts = [beds.available for beds in hospital.icu_beds.values()]
    return any(count is not None and count > 0 for count in counts) or all(count is None for count in counts)
