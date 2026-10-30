"""최종 선정 fallback 테스트. PRD_v0.1.md F-09의 완료조건(직선거리 정렬, 문장 틀, "비고 미반영" 경고)을 확인한다."""

from dataclasses import replace

import pytest
from fake_hospital_repository import make_hospital

from aimp.domain.eta import Eta, EtaMethod
from aimp.domain.hospital import BedCount
from aimp.domain.patient import SevereJudgment
from aimp.domain.types import HospitalCategory, Level, WarningCode
from aimp.engines.capability import CandidateHospital
from aimp.engines.guideline import LevelCondition
from aimp.selection import fallback
from aimp.selection.reasons import PatientContext

REC = HospitalCategory.REGIONAL_EMERGENCY_CENTER
LEC = HospitalCategory.LOCAL_EMERGENCY_CENTER
PATIENT = PatientContext(
    condition=LevelCondition(Level.L0, frozenset({REC, LEC})),
    severe_judgment=SevereJudgment(severe_type=None, category=None, required_resources=frozenset()),
    assessment=None,
)
TMAP_9_MIN = Eta("H", EtaMethod.TMAP, 5.5, 540, None)
STRAIGHT_LINE = Eta("H", EtaMethod.STRAIGHT_LINE, 4.2, None, None)


def _candidate(hospital_id: str = "H", distance_km: float = 4.2, stale: bool = False, **changes) -> CandidateHospital:
    """make_hospital(지역응급의료센터)에서 changes만 바꾼 후보 병원."""
    return CandidateHospital(replace(make_hospital(hospital_id, distance_km, LEC), **changes), stale_beds=stale)


def _ids(candidates: list[CandidateHospital]) -> list[str]:
    return [candidate.hospital.hospital_id for candidate in candidates]


def test_select_sorts_by_distance_and_keeps_count():
    """직선거리가 가까운 순으로 정렬해 앞의 count개만 고르는지 확인한다. 직선거리가 같으면 hospital_id 순이다."""
    candidates = [_candidate("C", 3.2), _candidate("A", 12.3), _candidate("D", 0.8), _candidate("B", 3.2)]

    assert _ids(fallback.select(candidates, 3, None, [])) == ["D", "B", "C"]


def test_select_returns_all_when_fewer_than_count():
    assert _ids(fallback.select([_candidate("A", 2.0), _candidate("B", 1.0)], 10, None, [])) == ["B", "A"]


@pytest.mark.parametrize(("remark", "warned"), [("계명대 동산병원 희망", True), (None, False), ("", False)])
def test_select_warns_remark_not_applied(remark, warned):
    """비고가 있으면 "비고 미반영" 경고를 넣고, 없거나 빈 문자열이면 넣지 않는지 확인한다."""
    warnings: list[WarningCode] = []

    fallback.select([_candidate()], 1, remark, warnings)

    assert warnings == ([WarningCode.REMARK_NOT_APPLIED] if warned else [])


@pytest.mark.parametrize(
    ("candidate", "eta", "expected"),
    [
        (
            _candidate(er_beds=BedCount(4, None)),
            TMAP_9_MIN,
            "지역응급의료센터 조건 충족, 직선거리 4.2km, 응급실 가용병상 4, 도착 예정 9분",
        ),
        (
            _candidate(stale=True, er_beds=BedCount(4, None)),
            TMAP_9_MIN,
            "지역응급의료센터 조건 충족, 직선거리 4.2km, 응급실 가용병상 4(병상 정보 오래됨), 도착 예정 9분",
        ),
        (_candidate(er_beds=BedCount(None, None)), TMAP_9_MIN, "지역응급의료센터 조건 충족, 직선거리 4.2km, 도착 예정 9분"),
        (_candidate(er_beds=BedCount(4, None)), STRAIGHT_LINE, "지역응급의료센터 조건 충족, 직선거리 4.2km, 응급실 가용병상 4"),
    ],
    ids=["all-values", "stale-beds", "no-er-beds", "straight-line-eta"],
)
def test_reason_sentence(candidate, eta, expected):
    """병원 분류 조건 충족, 직선거리, 응급실 가용병상을 이 순서로 채우고 Tmap ETA API로 구한 ETA를 붙이는지,
    병상 정보가 오래됐으면 표시하고 응급실 가용병상 값이 없으면 그 사유를 빼는지 확인한다."""
    assert fallback.reason(candidate, PATIENT, eta) == expected
