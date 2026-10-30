"""진료 역량 규칙 엔진(C) 테스트. PRD_v0.1.md F-13 '진료 역량 규칙 엔진'의 조건과 병상 신선도 태그를 확인한다."""

from datetime import datetime, timedelta

import pytest

from aimp.common.settings import settings
from aimp.domain.hospital import (
    AcceptanceStatus,
    BedCount,
    CongestionStatus,
    DiseaseAcceptance,
    Hospital,
    IcuBedType,
)
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Department, PatientCategory, Resource, SevereDiseaseCode, WarningCode
from aimp.engines import capability
from aimp.engines.capability import CandidateHospital

NO_BEDS = BedCount(available=None, total=None)
QUERIED_AT = datetime(2026, 10, 30, 14, 0, 0)  # 조회 시각. 시간대 정보 없는 KST
FRESH = QUERIED_AT - timedelta(minutes=5)  # 임계치(15분) 안의 갱신 시각
STALE = QUERIED_AT - timedelta(minutes=settings.bed_data_max_age_minutes + 1)
NOT_SEVERE = SevereJudgment(severe_type=None, category=None, required_resources=frozenset())


def _hospital(
    hospital_id: str,
    er_available: int | None = 1,
    icu_available: list[int | None] | None = None,
    beds_updated_at: datetime | None = FRESH,
    disease_acceptance: dict[str, AcceptanceStatus] | None = None,
    departments: frozenset[Department] = frozenset(),
    delivery_room: bool | None = None,
) -> Hospital:
    """icu_available은 중환자실 병상 종류(일반, 신경과, ...) 순서의 가용병상 수다. None이면 중환자실 병상이 없다.

    disease_acceptance는 중증질환 코드별 수용가능 값이다. None이면 수용가능 항목이 없다.
    """
    return Hospital(
        hospital_id=hospital_id,
        name=hospital_id,
        longitude=127.0,
        latitude=37.0,
        distance_km=1.0,
        categories=frozenset(),
        departments=departments,
        er_beds=BedCount(available=er_available, total=None),
        icu_beds={bed_type: BedCount(count, None) for bed_type, count in zip(IcuBedType, icu_available or [])},
        operating_room_beds=NO_BEDS,
        ward_beds=NO_BEDS,
        resuscitation_room=NO_BEDS,
        beds_updated_at=beds_updated_at,
        congestion=None,
        congestion_status=CongestionStatus.NO_DATA,
        disease_acceptance={
            code: DiseaseAcceptance(status, restriction=None) for code, status in (disease_acceptance or {}).items()
        },
        equipment={},
        delivery_room=delivery_room,
        block_messages=(),
    )


def _filter(
    hospitals: list[Hospital], category: PatientCategory = PatientCategory.MINOR_TRAUMA
) -> tuple[list[CandidateHospital], list[WarningCode]]:
    return capability.filter_candidates(hospitals, NOT_SEVERE, None, category, QUERIED_AT)


def _ids(candidates: list[CandidateHospital]) -> list[str]:
    return [candidate.hospital.hospital_id for candidate in candidates]


@pytest.fixture
def require_icu_beds(monkeypatch):
    monkeypatch.setattr(capability, "settings", settings.model_copy(update={"require_icu_beds": True}))


def test_removes_hospitals_without_er_beds():
    """응급실 가용병상이 0인 병원은 빠지고, 1 이상인 병원과 API가 값을 주지 않은 병원은 남는지 확인한다."""
    hospitals = [_hospital("ZERO", er_available=0), _hospital("ONE", er_available=1), _hospital("NONE", None)]

    candidates, warnings = _filter(hospitals)

    assert _ids(candidates) == ["ONE", "NONE"]
    assert not any(candidate.stale_beds for candidate in candidates)
    assert warnings == []


def test_keeps_stale_hospital_with_tag():
    """병상 값이 오래되었거나 갱신 시각이 없는 병원은 응급실 가용병상이 0이어도 남고, 태그가 붙고, 병상 값이 바뀌지 않는지 확인한다."""
    old = _hospital("OLD", er_available=0, beds_updated_at=STALE)
    missing = _hospital("MISSING", er_available=0, beds_updated_at=None)

    candidates, warnings = _filter([old, missing, _hospital("FRESH")])

    assert candidates == [
        CandidateHospital(old, stale_beds=True),
        CandidateHospital(missing, stale_beds=True),
        CandidateHospital(_hospital("FRESH"), stale_beds=False),
    ]
    assert old.er_beds == BedCount(available=0, total=None)
    assert warnings == [WarningCode.STALE_BED_DATA]


@pytest.mark.parametrize(
    ("age_minutes", "stale"),
    [(settings.bed_data_max_age_minutes, False), (settings.bed_data_max_age_minutes + 1, True)],
)
def test_stale_threshold_boundary(age_minutes, stale):
    """조회 시각과 갱신 시각의 차이가 임계치와 같으면 태그가 붙지 않고, 1분 넘으면 붙는지 확인한다."""
    hospital = _hospital("A", beds_updated_at=QUERIED_AT - timedelta(minutes=age_minutes))

    candidates, warnings = _filter([hospital])

    assert candidates == [CandidateHospital(hospital, stale_beds=stale)]
    assert warnings == ([WarningCode.STALE_BED_DATA] if stale else [])


ICU_HOSPITALS = [
    _hospital("ZERO", icu_available=[0, 0, 0, 0]),
    _hospital("ZERO_AND_NONE", icu_available=[0, None, None, None]),
    _hospital("ONE", icu_available=[0, 1, 0, 0]),
    _hospital("ALL_NONE", icu_available=[None, None, None, None]),
    _hospital("STALE_ZERO", icu_available=[0, 0, 0, 0], beds_updated_at=STALE),
]


@pytest.mark.usefixtures("require_icu_beds")
@pytest.mark.parametrize(
    "category",
    [
        PatientCategory.SEVERE_TRAUMA,
        PatientCategory.SEVERE_NON_TRAUMA,
        PatientCategory.STROKE_SUSPECTED,
        PatientCategory.STROKE_SCREENING_POSITIVE,
    ],
)
def test_icu_condition_applies_to_severe_patient(category):
    """require_icu_beds가 true면 중증 환자에게 중환자실 조건이 적용되는지 확인한다.

    어느 종류도 가용병상이 1 이상이 아닌 병원은 빠지고, 모든 종류의 값이 없는 병원과 태그가 붙은 병원은 남는다.
    """
    candidates, _ = _filter(ICU_HOSPITALS, category)

    assert _ids(candidates) == ["ONE", "ALL_NONE", "STALE_ZERO"]


@pytest.mark.usefixtures("require_icu_beds")
@pytest.mark.parametrize("category", [PatientCategory.MINOR_TRAUMA, PatientCategory.MINOR_NON_TRAUMA])
def test_icu_condition_skips_minor_patient(category):
    """require_icu_beds가 true여도 경증 환자에게는 중환자실 조건이 적용되지 않는지 확인한다."""
    candidates, _ = _filter(ICU_HOSPITALS, category)

    assert _ids(candidates) == [hospital.hospital_id for hospital in ICU_HOSPITALS]


def test_icu_condition_off_by_setting(monkeypatch):
    """require_icu_beds가 false면 중증 환자에게도 중환자실 조건이 적용되지 않는지 확인한다."""
    monkeypatch.setattr(capability, "settings", settings.model_copy(update={"require_icu_beds": False}))

    candidates, _ = _filter(ICU_HOSPITALS, PatientCategory.SEVERE_TRAUMA)

    assert len(candidates) == len(ICU_HOSPITALS)


def test_cardiac_arrest_skips_all_conditions():
    """심폐정지 환자에게는 응급실 가용병상이 0인 병원도 남는지 확인한다."""
    hospital = _hospital("ZERO", er_available=0)

    candidates, warnings = _filter([hospital], PatientCategory.CARDIAC_ARREST)

    assert candidates == [CandidateHospital(hospital, stale_beds=False)]
    assert warnings == []


def _assessment(
    severe_disease_code: SevereDiseaseCode | None = None, required_depts: tuple[Department, ...] = ()
) -> PatientAssessment:
    return PatientAssessment(
        is_trauma=False,
        required_depts=required_depts,
        supportive_depts=(Department.ANESTHESIOLOGY,),
        severe_disease_code=severe_disease_code,
        trauma_criteria=(),
    )


def _filter_with_assessment(
    hospitals: list[Hospital], assessment: PatientAssessment | None
) -> tuple[list[CandidateHospital], list[WarningCode]]:
    return capability.filter_candidates(hospitals, NOT_SEVERE, assessment, PatientCategory.SEVERE_NON_TRAUMA, QUERIED_AT)


STROKE = SevereDiseaseCode.MKIOSKTY2  # [재관류중재술] 뇌경색
DISEASE_HOSPITALS = [
    _hospital("Y", disease_acceptance={STROKE: AcceptanceStatus.AVAILABLE}),
    _hospital("UNAVAILABLE", disease_acceptance={STROKE: AcceptanceStatus.UNAVAILABLE}),
    _hospital("NOT_PROVIDED", disease_acceptance={STROKE: AcceptanceStatus.NOT_PROVIDED}),
    _hospital("NO_KEY", disease_acceptance={SevereDiseaseCode.MKIOSKTY1: AcceptanceStatus.AVAILABLE}),
]


def test_removes_hospitals_not_accepting_severe_disease():
    """중증응급질환 코드가 mkioskty2인 환자에게 그 코드가 Y인 병원은 남고, 불가능·정보미제공·키 없음인 병원은 빠지는지 확인한다."""
    candidates, _ = _filter_with_assessment(DISEASE_HOSPITALS, _assessment(STROKE))

    assert _ids(candidates) == ["Y"]


def test_disease_condition_ignores_stale_tag():
    """병상 정보 오래됨 태그가 붙는 병원에도 중증응급질환 수용가능 조건이 적용되는지 확인한다."""
    hospitals = [
        _hospital("STALE_Y", beds_updated_at=STALE, disease_acceptance={STROKE: AcceptanceStatus.AVAILABLE}),
        _hospital("STALE_UNAVAILABLE", beds_updated_at=STALE, disease_acceptance={STROKE: AcceptanceStatus.UNAVAILABLE}),
    ]

    candidates, _ = _filter_with_assessment(hospitals, _assessment(STROKE))

    assert _ids(candidates) == ["STALE_Y"]


def test_disease_condition_skipped_when_assessment_failed():
    """환자 상태 판단 결과가 None이면 수용가능 값이 불가능인 병원도 남는지 확인한다."""
    candidates, _ = _filter_with_assessment(DISEASE_HOSPITALS, None)

    assert _ids(candidates) == [hospital.hospital_id for hospital in DISEASE_HOSPITALS]


def test_disease_condition_skipped_without_severe_disease_code():
    """환자 상태 판단 결과의 severe_disease_code가 None이면 중증응급질환 수용가능 조건을 적용하지 않는지 확인한다."""
    candidates, _ = _filter_with_assessment(DISEASE_HOSPITALS, _assessment(None))

    assert _ids(candidates) == [hospital.hospital_id for hospital in DISEASE_HOSPITALS]


ORTHO = frozenset({Department.ORTHOPEDIC_SURGERY})
ORTHO_AND_GS = frozenset({Department.ORTHOPEDIC_SURGERY, Department.GENERAL_SURGERY})
NEEDS_ORTHO = _assessment(required_depts=(Department.ORTHOPEDIC_SURGERY,))  # 필수 진료과가 정형외과인 환자


def test_removes_hospitals_without_required_dept():
    """필수 진료과가 정형외과면 정형외과가 있는 병원은 남고, 없는 병원은 태그가 붙어도 빠지는지 확인한다.

    보조 진료과(마취통증의학과)는 거르는 데 쓰지 않는다.
    """
    hospitals = [
        _hospital("ORTHO", departments=ORTHO),
        _hospital("NONE"),
        _hospital("GS", departments=frozenset({Department.GENERAL_SURGERY})),
        _hospital("STALE_NONE", beds_updated_at=STALE),
    ]

    candidates, _ = _filter_with_assessment(hospitals, NEEDS_ORTHO)

    assert _ids(candidates) == ["ORTHO"]


def test_removes_hospitals_missing_one_of_two_required_depts():
    """필수 진료과가 두 개면 둘 다 있는 병원만 남고 하나만 있는 병원은 빠지는지 확인한다."""
    hospitals = [_hospital("ORTHO", departments=ORTHO), _hospital("BOTH", departments=ORTHO_AND_GS)]

    assessment = _assessment(required_depts=(Department.ORTHOPEDIC_SURGERY, Department.GENERAL_SURGERY))

    candidates, _ = _filter_with_assessment(hospitals, assessment)

    assert _ids(candidates) == ["BOTH"]


@pytest.mark.parametrize("assessment", [None, _assessment()], ids=["assessment_none", "required_depts_empty"])
def test_required_dept_condition_skipped(assessment):
    """환자 상태 판단 결과가 None이거나 필수 진료과가 비어 있으면 진료과 조건을 적용하지 않는지 확인한다."""
    hospitals = [_hospital("NONE"), _hospital("ORTHO", departments=ORTHO)]

    candidates, _ = _filter_with_assessment(hospitals, assessment)

    assert _ids(candidates) == ["NONE", "ORTHO"]


def test_cardiac_arrest_skips_required_dept_condition():
    """심폐정지 환자에게는 필수 진료과가 없는 병원도 남는지 확인한다."""
    hospital = _hospital("NONE")

    candidates, _ = capability.filter_candidates(
        [hospital], NOT_SEVERE, NEEDS_ORTHO, PatientCategory.CARDIAC_ARREST, QUERIED_AT
    )

    assert _ids(candidates) == ["NONE"]


def _filter_with_resources(
    hospitals: list[Hospital],
    resources: set[Resource],
    category: PatientCategory = PatientCategory.MINOR_NON_TRAUMA,
    assessment: PatientAssessment | None = None,
) -> list[CandidateHospital]:
    judgment = SevereJudgment(severe_type=None, category=None, required_resources=frozenset(resources))
    candidates, _ = capability.filter_candidates(hospitals, judgment, assessment, category, QUERIED_AT)
    return candidates


Y = AcceptanceStatus.AVAILABLE
UNAVAILABLE = AcceptanceStatus.UNAVAILABLE
NOT_PROVIDED = AcceptanceStatus.NOT_PROVIDED
MI = SevereDiseaseCode.MKIOSKTY1  # [재관류중재술] 심근경색
DELIVERY = SevereDiseaseCode.MKIOSKTY16  # [산부인과응급] 분만
PEDIATRICS = frozenset({Department.PEDIATRICS})
STROKE_CODES = (SevereDiseaseCode.MKIOSKTY2, SevereDiseaseCode.MKIOSKTY3, SevereDiseaseCode.MKIOSKTY4)


@pytest.mark.parametrize(
    ("resource", "hospitals", "expected"),
    [
        (
            Resource.STROKE_TREATMENT,
            [
                _hospital("MKIOSKTY2_Y", disease_acceptance={SevereDiseaseCode.MKIOSKTY2: Y}),
                _hospital("MKIOSKTY3_Y", disease_acceptance={SevereDiseaseCode.MKIOSKTY3: Y}),
                _hospital("MKIOSKTY4_Y", disease_acceptance={STROKE: UNAVAILABLE, SevereDiseaseCode.MKIOSKTY4: Y}),
                _hospital("UNAVAILABLE", disease_acceptance=dict.fromkeys(STROKE_CODES, UNAVAILABLE)),
                _hospital("NOT_PROVIDED", disease_acceptance=dict.fromkeys(STROKE_CODES, NOT_PROVIDED)),
                _hospital("NO_KEY", disease_acceptance={MI: Y}),
            ],
            ["MKIOSKTY2_Y", "MKIOSKTY3_Y", "MKIOSKTY4_Y"],
        ),
        (
            Resource.MI_REPERFUSION,
            [
                _hospital("Y", disease_acceptance={MI: Y}),
                _hospital("UNAVAILABLE", disease_acceptance={MI: UNAVAILABLE}),
                _hospital("NOT_PROVIDED", disease_acceptance={MI: NOT_PROVIDED}),
                _hospital("NO_KEY", disease_acceptance={SevereDiseaseCode.MKIOSKTY2: Y}),
            ],
            ["Y"],
        ),
        (
            Resource.PEDIATRIC_EMERGENCY,
            [
                _hospital("PEDIATRICS", departments=PEDIATRICS),
                _hospital("NONE", departments=frozenset({Department.INTERNAL_MEDICINE})),
                _hospital("STALE_NONE", beds_updated_at=STALE),
            ],
            ["PEDIATRICS"],
        ),
    ],
    ids=["stroke", "mi", "pediatric"],
)
def test_removes_hospitals_without_required_resource(resource, hospitals, expected):
    """특수 자원마다 PRD F-02 판정 규칙 표의 조건을 만족하는 병원만 남는지 확인한다.

    수용가능 값이 불가능·정보미제공이거나 키가 없는 병원, 소아청소년과가 없는 병원은 빠진다.
    소아청소년과가 없는 병원은 병상 정보 오래됨 태그가 붙어도 빠진다.
    """
    candidates = _filter_with_resources(hospitals, {resource})

    assert _ids(candidates) == expected


DELIVERY_HOSPITALS = [
    _hospital("MKIOSKTY16_Y", disease_acceptance={DELIVERY: Y}),
    _hospital("DELIVERY_ROOM", delivery_room=True),
    _hospital("NEITHER", disease_acceptance={DELIVERY: UNAVAILABLE}, delivery_room=False),
    _hospital("NO_DATA"),
]


def _delivery_tags(candidates: list[CandidateHospital]) -> dict[str, bool]:
    return {candidate.hospital.hospital_id: candidate.can_deliver for candidate in candidates}


def test_delivery_resource_tags_without_filtering():
    """분만 자원이 붙은 환자에게 mkioskty16이 Y인 병원과 분만실이 가용인 병원에는 "분만 가능" 태그가 붙고,
    둘 다 아닌 병원은 태그 없이 후보에 남는지 확인한다."""
    candidates = _filter_with_resources(DELIVERY_HOSPITALS, {Resource.DELIVERY})

    expected = {"MKIOSKTY16_Y": True, "DELIVERY_ROOM": True, "NEITHER": False, "NO_DATA": False}
    assert _delivery_tags(candidates) == expected


def test_no_delivery_tag_without_delivery_resource():
    """분만 자원이 없는 환자에게는 분만이 가능한 병원에도 "분만 가능" 태그가 붙지 않는지 확인한다."""
    candidates = _filter_with_resources(DELIVERY_HOSPITALS, set())

    assert not any(candidate.can_deliver for candidate in candidates)


def test_pediatric_and_delivery_resources():
    """특수 자원이 소아 + 분만이면 소아청소년과가 있는 병원만 남고, 그중 분만이 가능한 병원에 태그가 붙는지 확인한다."""
    hospitals = [
        _hospital("PEDIATRICS_DELIVERY", departments=PEDIATRICS, delivery_room=True),
        _hospital("PEDIATRICS", departments=PEDIATRICS),
        _hospital("DELIVERY", disease_acceptance={DELIVERY: Y}),
    ]

    candidates = _filter_with_resources(hospitals, {Resource.PEDIATRIC_EMERGENCY, Resource.DELIVERY})

    assert _delivery_tags(candidates) == {"PEDIATRICS_DELIVERY": True, "PEDIATRICS": False}


def test_removes_hospitals_missing_one_of_two_resources():
    """분만을 뺀 특수 자원이 둘이면 둘 다 갖춘 병원만 남는지 확인한다."""
    hospitals = [
        _hospital("BOTH", departments=PEDIATRICS, disease_acceptance={MI: Y}),
        _hospital("PEDIATRICS", departments=PEDIATRICS),
        _hospital("MI", disease_acceptance={MI: Y}),
    ]

    candidates = _filter_with_resources(hospitals, {Resource.PEDIATRIC_EMERGENCY, Resource.MI_REPERFUSION})

    assert _ids(candidates) == ["BOTH"]


def test_cardiac_arrest_skips_resource_conditions_and_tag():
    """15세 미만이거나 임산부인 심폐정지 환자에게는 특수 자원 조건과 "분만 가능" 태그가 적용되지 않는지 확인한다."""
    hospitals = [_hospital("NONE"), _hospital("DELIVERY_ROOM", delivery_room=True)]

    candidates = _filter_with_resources(
        hospitals, {Resource.PEDIATRIC_EMERGENCY, Resource.DELIVERY}, PatientCategory.CARDIAC_ARREST
    )

    assert _delivery_tags(candidates) == {"NONE": False, "DELIVERY_ROOM": False}


@pytest.mark.parametrize("assessment", [None, _assessment()], ids=["assessment_none", "assessment_ok"])
def test_resource_conditions_apply_regardless_of_assessment(assessment):
    """환자 상태 판단 결과가 None이어도 특수 자원 조건과 "분만 가능" 태그가 적용되는지 확인한다."""
    hospitals = [_hospital("NONE"), _hospital("PEDIATRICS_DELIVERY", departments=PEDIATRICS, delivery_room=True)]

    resources = {Resource.PEDIATRIC_EMERGENCY, Resource.DELIVERY}

    candidates = _filter_with_resources(hospitals, resources, assessment=assessment)

    assert _delivery_tags(candidates) == {"PEDIATRICS_DELIVERY": True}
