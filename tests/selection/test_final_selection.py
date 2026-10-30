"""최종 선정(E) 테스트."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fake_hospital_repository import make_hospital
from fake_llm import FakeLlmClient

from aimp.api.request import Patient
from aimp.common.settings import settings
from aimp.domain.hospital import AcceptanceStatus, BedCount, CongestionStatus, DiseaseAcceptance, IcuBedType
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Department, HospitalCategory, PatientCategory, SevereDiseaseCode
from aimp.engines import guideline
from aimp.engines.capability import CandidateHospital
from aimp.ports.llm import LlmFailure, LlmOutput
from aimp.selection import final_selection
from aimp.selection.final_selection import DetourReason, FinalSelection, SelectedHospital
from aimp.selection.reasons import PatientContext, ReasonTemplate

FIXTURES = Path(__file__).parents[1] / "fixtures"

LEI = HospitalCategory.LOCAL_EMERGENCY_INSTITUTION
MINOR_TRAUMA = PatientCategory.MINOR_TRAUMA
CARDIAC_ARREST = PatientCategory.CARDIAC_ARREST
OPEN_FRACTURE = PatientAssessment(
    is_trauma=True,
    required_depts=(Department.ORTHOPEDIC_SURGERY,),
    supportive_depts=(Department.PLASTIC_SURGERY,),
    severe_disease_code=None,
    trauma_criteria=(),
)
CONTEXT = PatientContext(
    condition=guideline.levels_for(MINOR_TRAUMA)[0],  # L0: 지역응급의료기관
    severe_judgment=SevereJudgment(severe_type=None, category=None, required_resources=frozenset()),
    assessment=OPEN_FRACTURE,
)


def _candidate(hospital_id: str, distance_km: float, stale: bool = False, **changes) -> CandidateHospital:
    """make_hospital(지역응급의료기관, 모든 진료과)에서 changes만 바꾼 후보 병원."""
    hospital = replace(make_hospital(hospital_id, distance_km, LEI), **changes)
    return CandidateHospital(hospital, stale_beds=stale)


def _example_candidates() -> list[CandidateHospital]:
    """발등 개방성 골절 예시의 후보 병원 4곳. H4는 가장 가까운 H1보다 3km 넘게 멀어 "우회" 태그가 붙는다."""
    return [
        _candidate("H1", 1.5, er_beds=BedCount(0, 10), congestion_status=CongestionStatus.CROWDED),
        _candidate(
            "H2",
            3.0,
            departments=frozenset({Department.ORTHOPEDIC_SURGERY}),
            er_beds=BedCount(3, 12),
            block_messages=("[정형외과] 수지접합 불가",),
        ),
        _candidate("H3", 4.2, stale=True, er_beds=BedCount(8, 20), icu_beds={IcuBedType.GENERAL: BedCount(2, 8)}),
        _candidate("H4", 5.1, er_beds=BedCount(6, 15), congestion_status=CongestionStatus.RELAXED),
    ]


def _patient(example_patient: dict, remark: str | None = "자유서술") -> Patient:
    example_patient["remark"] = remark
    return Patient.model_validate(example_patient)


def _output(
    *numbers: int, detour_reason: DetourReason | None = None, reasons=None, quotes=None
) -> FinalSelection:
    """후보 번호 순서대로 추천한 출력. reasons·quotes에 번호별 사유·비고 인용을 주지 않으면 distance 하나, 인용 없음이다."""
    reasons, quotes = reasons or {}, quotes or {}
    return FinalSelection(
        recommendations=tuple(
            SelectedHospital(
                candidate_no=no, reasons=reasons.get(no, (ReasonTemplate.DISTANCE,)), remark_quote=quotes.get(no)
            )
            for no in numbers
        ),
        detour_reason=detour_reason,
    )


def _select(patient: Patient, output: FinalSelection, recommend_count: int = 3, category=MINOR_TRAUMA, candidates=None):
    client = FakeLlmClient(LlmOutput(parsed=output, raw=output.model_dump_json()))
    result = final_selection.select(
        patient, CONTEXT, category, candidates or _example_candidates(), recommend_count, client
    )
    return result, client


def test_open_fracture_messages_match_fixtures(example_patient):
    """발등 개방성 골절 예시로 만든 system·user 메시지가 기대 파일과 같은지 확인한다.

    프롬프트나 LLM 입력 객체를 바꾸면 이 테스트가 실패하므로, 바뀐 메시지를 검토한 뒤 기대 파일을 함께 고친다.
    """
    messages = final_selection.build_messages(
        Patient.model_validate(example_patient), CONTEXT, MINOR_TRAUMA, _example_candidates(), 3
    )

    assert messages == [
        {"role": "system", "content": (FIXTURES / "final_selection_system.md").read_text(encoding="utf-8")},
        {"role": "user", "content": (FIXTURES / "final_selection_user.json").read_text(encoding="utf-8")},
    ]


@pytest.mark.parametrize("remark", [None, "", "  "])
def test_input_omits_empty_remark(example_patient, remark):
    """비고가 비었거나 생략되면 LLM 입력 객체에 비고 키가 없는지 확인한다."""
    data = final_selection.build_input(
        _patient(example_patient, remark), CONTEXT, MINOR_TRAUMA, _example_candidates(), 3
    )

    assert "remark" not in data
    assert "remark" not in data["patient"]


def test_input_omits_assessment_when_failed(example_patient):
    """환자 상태 판단이 실패했으면 LLM 입력 객체에 환자 상태 판단 결과 키가 없는지 확인한다."""
    context = replace(CONTEXT, assessment=None)

    data = final_selection.build_input(_patient(example_patient), context, MINOR_TRAUMA, _example_candidates(), 3)

    assert "assessment" not in data


def test_input_includes_patient_severe_disease_acceptance(example_patient):
    """중증질환 수용가능은 환자의 중증응급질환 코드의 값만 넣는지 확인한다."""
    code = SevereDiseaseCode.MKIOSKTY20
    context = replace(CONTEXT, assessment=OPEN_FRACTURE.model_copy(update={"severe_disease_code": code}))
    candidate = _candidate("H1", 1.5, disease_acceptance={code: DiseaseAcceptance(AcceptanceStatus.UNAVAILABLE, None)})

    data = final_selection.build_input(_patient(example_patient), context, MINOR_TRAUMA, [candidate], 3)

    assert data["assessment"]["severe_disease"] == "[사지접합] 수족지접합"
    assert data["candidates"][0]["severe_disease_acceptance"] == "불가능"


@pytest.mark.parametrize(
    ("distance_km", "expected"),
    [(7.2, False), (7.3, True)],
    ids=["equal-to-threshold", "over-threshold"],
)
def test_detour_threshold(distance_km, expected):
    """1순위 병원이 가장 가까운 후보보다 X km(3.0) 멀면 우회가 아니고, X km를 넘으면 우회인지 확인한다.

    7.2 - 4.2는 부동소수점으로 3.0000000000000004라서, 반올림하지 않으면 같은 경우도 우회가 된다.
    """
    assert settings.detour_threshold_km == 3.0
    nearest, first = _candidate("near", 4.2), _candidate("far", distance_km)

    assert final_selection.is_detour(first, [nearest, first]) is expected


def test_select_fills_reasons(example_patient):
    """정상 출력이면 후보 번호의 병원을 고르고, LLM이 고른 순서대로 사유를 채우는지 확인한다.

    값이 없는 템플릿(H3의 delivery, H1의 icu_beds)과 같은 문장은 버리고, 남은 사유가 없으면 distance를 넣는다.
    """
    output = _output(
        3,
        2,
        1,
        reasons={
            3: (ReasonTemplate.ER_BEDS, ReasonTemplate.REQUIRED_DEPT, ReasonTemplate.DELIVERY, ReasonTemplate.ER_BEDS),
            2: (ReasonTemplate.REMARK, ReasonTemplate.ER_BEDS),
            1: (ReasonTemplate.ICU_BEDS,),  # H1은 중환자실 가용병상 값이 없다
        },
        quotes={2: "자유"},
    )

    result, client = _select(_patient(example_patient), output)

    assert client.calls[0].response_format is FinalSelection
    assert client.calls[0].timeout == settings.llm_timeout_seconds
    assert [r.candidate.hospital.hospital_id for r in result.recommendations] == ["H3", "H2", "H1"]
    assert [r.reasons for r in result.recommendations] == [
        ("응급실 가용병상 8(병상 정보 오래됨)", "정형외과 진료 가능"),
        ('비고: "자유"', "응급실 가용병상 3"),
        ("직선거리 1.5km",),
    ]
    assert (result.detour, result.detour_reason) == (False, None)


def test_select_drops_detour_reason_when_not_detour(example_patient):
    """1순위가 우회가 아니면 LLM이 고른 우회 사유를 버리는지 확인한다."""
    output = _output(1, 2, 3, detour_reason=DetourReason.BED_AVAILABILITY)

    result, _ = _select(_patient(example_patient), output)

    assert (result.detour, result.detour_reason) == (False, None)


def test_select_marks_detour(example_patient):
    """1순위가 우회이고 우회 사유가 있으면 우회로 표시하는지 확인한다."""
    output = _output(4, 3, 2, detour_reason=DetourReason.BED_AVAILABILITY)

    result, _ = _select(_patient(example_patient), output)

    assert (result.detour, result.detour_reason) == (True, DetourReason.BED_AVAILABILITY)


def test_select_accepts_all_candidates_when_fewer_than_n(example_patient):
    """후보가 N개보다 적으면 후보를 모두 추천한 출력이 검증을 통과하는지 확인한다."""
    result, _ = _select(_patient(example_patient), _output(1, 2, 3, 4), recommend_count=10)

    assert len(result.recommendations) == 4


@pytest.mark.parametrize(
    ("output", "category", "remark"),
    [
        (_output(1, 2, 5), MINOR_TRAUMA, "자유서술"),  # 후보에 없는 번호
        (_output(0, 1, 2), MINOR_TRAUMA, "자유서술"),  # 후보 번호는 1부터
        (_output(1, 2, 1), MINOR_TRAUMA, "자유서술"),  # 중복
        (_output(1, 2), MINOR_TRAUMA, "자유서술"),  # N개보다 적음
        (_output(1, 2, 3, 4), MINOR_TRAUMA, "자유서술"),  # N개보다 많음
        (_output(4, 1, 2), MINOR_TRAUMA, "자유서술"),  # 우회인데 우회 사유 없음
        # 심폐정지 환자의 1순위가 우회
        (_output(4, 1, 2, detour_reason=DetourReason.BED_AVAILABILITY), CARDIAC_ARREST, "자유서술"),
        # 비고 인용 문구가 비고 원문에 없음
        (_output(1, 2, 3, reasons={2: (ReasonTemplate.REMARK,)}, quotes={2: "환자 희망"}), MINOR_TRAUMA, "자유서술"),
        # 비고가 없는데 비고 인용
        (_output(1, 2, 3, reasons={2: (ReasonTemplate.REMARK,)}, quotes={2: "자유서술"}), MINOR_TRAUMA, None),
    ],
    ids=[
        "unknown-number",
        "zero-number",
        "duplicate-number",
        "too-few",
        "too-many",
        "detour-without-reason",
        "cardiac-arrest-detour",
        "quote-not-in-remark",
        "quote-without-remark",
    ],
)
def test_select_validation_failure(example_patient, output, category, remark):
    """출력 검증 항목마다 검증에 실패하면 '검증 실패'를 반환하는지 확인한다."""
    result, _ = _select(_patient(example_patient, remark), output, category=category)

    assert result == LlmFailure.VALIDATION_FAILED


@pytest.mark.parametrize("failure", list(LlmFailure))
def test_select_returns_llm_failure(example_patient, failure):
    """LLM 호출이 실패하면 그 실패 사유를 그대로 반환하는지 확인한다."""
    client = FakeLlmClient(failure)

    result = final_selection.select(
        _patient(example_patient), CONTEXT, MINOR_TRAUMA, _example_candidates(), 3, client
    )

    assert result == failure


def test_output_schema_in_system_prompt():
    """시스템 프롬프트에 출력 스키마가 들어가고, 채우지 않은 자리표시자가 없는지 확인한다."""
    schema = json.dumps(FinalSelection.model_json_schema(), ensure_ascii=False)

    assert schema in final_selection.SYSTEM_PROMPT
    assert "$" not in final_selection.SYSTEM_PROMPT.replace(schema, "")
