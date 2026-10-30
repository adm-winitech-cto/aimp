"""진료 역량 규칙 엔진(C) 테스트. PRD_v0.1.md F-13 '진료 역량 규칙 엔진'의 가용병상 조건과 병상 신선도 태그를 확인한다."""

from datetime import datetime, timedelta

import pytest

from aimp.common.settings import settings
from aimp.domain.hospital import BedCount, CongestionStatus, Hospital, IcuBedType
from aimp.domain.patient import SevereJudgment
from aimp.domain.types import PatientCategory, WarningCode
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
) -> Hospital:
    """icu_available은 중환자실 병상 종류(일반, 신경과, ...) 순서의 가용병상 수다. None이면 중환자실 병상이 없다."""
    return Hospital(
        hospital_id=hospital_id,
        name=hospital_id,
        longitude=127.0,
        latitude=37.0,
        distance_km=1.0,
        categories=frozenset(),
        departments=frozenset(),
        er_beds=BedCount(available=er_available, total=None),
        icu_beds={bed_type: BedCount(count, None) for bed_type, count in zip(IcuBedType, icu_available or [])},
        operating_room_beds=NO_BEDS,
        ward_beds=NO_BEDS,
        resuscitation_room=NO_BEDS,
        beds_updated_at=beds_updated_at,
        congestion=None,
        congestion_status=CongestionStatus.NO_DATA,
        disease_acceptance={},
        equipment={},
        delivery_room=None,
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
