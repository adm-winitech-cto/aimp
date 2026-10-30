"""추천 사유 템플릿 테스트."""

from dataclasses import replace
from datetime import datetime

import pytest
from fake_hospital_repository import make_hospital

from aimp.domain.eta import Eta, EtaMethod
from aimp.domain.hospital import AcceptanceStatus, BedCount, CongestionStatus, DiseaseAcceptance, IcuBedType
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Department, HospitalCategory, Level, Resource, SevereDiseaseCode
from aimp.engines.capability import CandidateHospital
from aimp.engines.guideline import LevelCondition
from aimp.selection import reasons
from aimp.selection.reasons import PatientContext, ReasonTemplate

REC = HospitalCategory.REGIONAL_EMERGENCY_CENTER
LEC = HospitalCategory.LOCAL_EMERGENCY_CENTER
MI = SevereDiseaseCode.MKIOSKTY1
L0_REC_LEC = LevelCondition(Level.L0, frozenset({REC, LEC}))


def _assessment(
    required_depts: tuple[Department, ...] = (), severe_disease_code: SevereDiseaseCode | None = None
) -> PatientAssessment:
    return PatientAssessment(
        is_trauma=False,
        required_depts=required_depts,
        supportive_depts=(),
        severe_disease_code=severe_disease_code,
        trauma_criteria=(),
    )


def _patient(
    assessment: PatientAssessment | None = None, resources: frozenset[Resource] = frozenset()
) -> PatientContext:
    return PatientContext(
        condition=L0_REC_LEC,
        severe_judgment=SevereJudgment(severe_type=None, category=None, required_resources=resources),
        assessment=assessment,
    )


def _candidate(stale: bool = False, can_deliver: bool = False, **changes) -> CandidateHospital:
    """make_hospital(모든 진료과, 모든 중증질환 Y, 직선거리 4.2km, 권역응급의료센터)에서 changes만 바꾼 후보 병원."""
    hospital = replace(make_hospital("H", 4.2, REC), **changes)
    return CandidateHospital(hospital, stale_beds=stale, can_deliver=can_deliver)


def _render(template, candidate=None, patient=None, quote=None):
    return reasons.render(template, candidate or _candidate(), patient or _patient(), quote)


ICU = {IcuBedType.GENERAL: BedCount(2, None), IcuBedType.NEUROLOGY: BedCount(None, None)}


@pytest.mark.parametrize(
    ("template", "candidate", "patient", "quote", "expected"),
    [
        (ReasonTemplate.GRADE, None, None, None, "권역응급의료센터 조건 충족"),
        (
            ReasonTemplate.REQUIRED_DEPT,
            None,
            _patient(_assessment((Department.ORTHOPEDIC_SURGERY, Department.GENERAL_SURGERY))),
            None,
            "정형외과·외과 진료 가능",
        ),
        (ReasonTemplate.SEVERE_DISEASE, None, _patient(_assessment(severe_disease_code=MI)), None,
         "[재관류중재술] 심근경색 수용 가능"),
        (
            ReasonTemplate.SPECIAL_RESOURCE,
            None,
            _patient(resources=frozenset({Resource.PEDIATRIC_EMERGENCY, Resource.MI_REPERFUSION, Resource.DELIVERY})),
            None,
            "심근경색 재관류중재술·소아 응급 진료 가능",
        ),
        (ReasonTemplate.ER_BEDS, _candidate(er_beds=BedCount(4, None)), None, None, "응급실 가용병상 4"),
        (ReasonTemplate.ICU_BEDS, _candidate(icu_beds=ICU), None, None, "중환자실 가용병상 2"),
        (ReasonTemplate.DELIVERY, _candidate(can_deliver=True), None, None, "분만 가능"),
        (ReasonTemplate.CONGESTION, _candidate(congestion_status=CongestionStatus.CROWDED), None, None, "응급실 혼잡"),
        (ReasonTemplate.DISTANCE, None, None, None, "직선거리 4.2km"),
        (ReasonTemplate.REMARK, None, None, "계명대 동산병원 희망", '비고: "계명대 동산병원 희망"'),
    ],
)
def test_render_fills_template(template, candidate, patient, quote, expected):
    """템플릿마다 값이 있으면 문장 틀에 값을 채우는지 확인한다."""
    assert _render(template, candidate, patient, quote) == expected


def test_every_template_has_sentence():
    """모든 템플릿에 문장 틀이 있는지 확인한다. 값을 모두 갖춘 후보와 환자로 채우면 None이 나오지 않는다."""
    candidate = _candidate(
        can_deliver=True, er_beds=BedCount(4, None), icu_beds=ICU, congestion_status=CongestionStatus.RELAXED
    )
    patient = _patient(_assessment((Department.ORTHOPEDIC_SURGERY,), MI), frozenset({Resource.MI_REPERFUSION}))

    assert all(_render(template, candidate, patient, "인용") is not None for template in ReasonTemplate)


@pytest.mark.parametrize(
    ("template", "candidate", "patient", "quote"),
    [
        # 병원 분류가 레벨 조건에 없음
        (ReasonTemplate.GRADE, _candidate(categories=frozenset({HospitalCategory.LOCAL_EMERGENCY_INSTITUTION})), None,
         None),
        (ReasonTemplate.REQUIRED_DEPT, None, _patient(None), None),  # 환자 상태 판단 실패
        (ReasonTemplate.REQUIRED_DEPT, None, _patient(_assessment()), None),  # 필수 진료과 없음
        # 필수 진료과가 병원에 없음(진료 역량 규칙 엔진을 끈 경우)
        (ReasonTemplate.REQUIRED_DEPT, _candidate(departments=frozenset()),
         _patient(_assessment((Department.ORTHOPEDIC_SURGERY,))), None),
        (ReasonTemplate.SEVERE_DISEASE, None, _patient(_assessment()), None),  # 중증응급질환 코드 없음
        (
            ReasonTemplate.SEVERE_DISEASE,
            _candidate(disease_acceptance={MI: DiseaseAcceptance(AcceptanceStatus.NOT_PROVIDED, None)}),
            _patient(_assessment(severe_disease_code=MI)),
            None,
        ),
        (ReasonTemplate.SPECIAL_RESOURCE, None, _patient(resources=frozenset({Resource.DELIVERY})), None),
        (ReasonTemplate.ER_BEDS, _candidate(er_beds=BedCount(None, None)), None, None),
        (ReasonTemplate.ICU_BEDS, _candidate(icu_beds={IcuBedType.GENERAL: BedCount(None, 3)}), None, None),
        (ReasonTemplate.DELIVERY, _candidate(can_deliver=False), None, None),
        (ReasonTemplate.CONGESTION, _candidate(congestion_status=CongestionStatus.NO_DATA), None, None),
        (ReasonTemplate.REMARK, None, None, None),
    ],
)
def test_render_drops_reason_without_value(template, candidate, patient, quote):
    """채울 값이 없으면 사유를 만들지 않는지(None) 확인한다."""
    assert _render(template, candidate, patient, quote) is None


@pytest.mark.parametrize(
    ("template", "changes", "expected"),
    [
        (ReasonTemplate.ER_BEDS, {"er_beds": BedCount(4, None)}, "응급실 가용병상 4(병상 정보 오래됨)"),
        (ReasonTemplate.ICU_BEDS, {"icu_beds": ICU}, "중환자실 가용병상 2(병상 정보 오래됨)"),
    ],
)
def test_stale_beds_suffix(template, changes, expected):
    """"병상 정보 오래됨" 태그가 붙은 병원이면 병상 수 뒤에 (병상 정보 오래됨)을 붙이는지 확인한다."""
    assert _render(template, _candidate(stale=True, **changes)) == expected


def _eta(method: EtaMethod, travel_seconds: int | None) -> Eta:
    arrival = datetime(2026, 10, 30, 18, 0) if travel_seconds is not None else None
    return Eta(hospital_id="H", method=method, distance_km=4.2, travel_seconds=travel_seconds, arrival_at=arrival)


@pytest.mark.parametrize(
    ("eta", "expected"),
    [
        (_eta(EtaMethod.TMAP, 250), "응급실 가용병상 4, 직선거리 4.2km, 도착 예정 4분"),
        (_eta(EtaMethod.TMAP, 20), "응급실 가용병상 4, 직선거리 4.2km, 도착 예정 1분"),
        (_eta(EtaMethod.STRAIGHT_LINE, None), "응급실 가용병상 4, 직선거리 4.2km"),
    ],
    ids=["tmap", "under-1-minute", "straight-line"],
)
def test_join_reasons(eta, expected):
    """사유를 순서대로 ', '로 이어 붙이고 None은 빼며, Tmap ETA면 마지막에 도착 예정 시간을 붙이는지 확인한다."""
    assert reasons.join_reasons(["응급실 가용병상 4", None, "직선거리 4.2km"], eta) == expected


@pytest.mark.parametrize(
    ("patient", "expected"),
    [
        (
            _patient(
                _assessment((Department.ORTHOPEDIC_SURGERY, Department.GENERAL_SURGERY)),
                frozenset({Resource.DELIVERY, Resource.PEDIATRIC_EMERGENCY}),
            ),
            ("정형외과·외과 진료 필요 예상", "소아 응급 진료·분만 필요 예상"),
        ),
        (_patient(_assessment((Department.ORTHOPEDIC_SURGERY,))), ("정형외과 진료 필요 예상",)),
        (_patient(resources=frozenset({Resource.MI_REPERFUSION})), ("심근경색 재관류중재술 필요 예상",)),
        (_patient(_assessment()), ()),
    ],
    ids=["depts-and-resources", "depts-only", "assessment-failed", "none"],
)
def test_patient_needs(patient, expected):
    """필수 진료과와 특수 자원을 "필요 예상" 사유로 이 순서로 만들고(특수 자원은 분만을 넣고 Resource 정의 순서),
    환자 상태 판단이 실패했거나 값이 없으면 그 사유를 빼는지 확인한다."""
    assert reasons.patient_needs(patient) == expected
