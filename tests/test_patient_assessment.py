"""환자 상태 판단(A1) 테스트."""

from pathlib import Path

import pytest
from fake_llm import FakeLlmClient
from pydantic import ValidationError

from transfer_recommender.api.request import Patient
from transfer_recommender.classification import patient_assessment
from transfer_recommender.domain.patient import PatientAssessment
from transfer_recommender.domain.types import (
    INJURY_FINDINGS,
    INJURY_MECHANISMS,
    SPECIAL_SITUATIONS,
    Department,
    TraumaCriterion,
    WarningCode,
)
from transfer_recommender.llm_client import LlmFailure, LlmOutput
from transfer_recommender.settings import settings

FIXTURES = Path(__file__).parent / "fixtures"

OPEN_FRACTURE = PatientAssessment(
    is_trauma=True,
    required_depts=(Department.ORTHOPEDIC_SURGERY,),
    supportive_depts=(Department.PLASTIC_SURGERY,),
    severe_disease_code=None,
    trauma_criteria=(),
)


def test_open_fracture_messages_match_fixtures(example_patient):
    """발등 개방성 골절 예시로 만든 system·user 메시지가 기대 파일과 같은지 확인한다.

    프롬프트나 LLM 입력 객체를 바꾸면 이 테스트가 실패하므로, 바뀐 메시지를 검토한 뒤 기대 파일을 함께 고친다.
    """
    messages = patient_assessment.build_messages(Patient.model_validate(example_patient))

    assert messages == [
        {"role": "system", "content": (FIXTURES / "patient_assessment_system.md").read_text(encoding="utf-8")},
        {"role": "user", "content": (FIXTURES / "patient_assessment_user.json").read_text(encoding="utf-8")},
    ]


def test_input_includes_remark_and_pregnancy_info(example_patient):
    """손상기전과 신체검사 소견이 비고에만 적힐 수 있고 임신 주수는 임산부 정보에 있으므로,
    LLM 입력 객체에 비고와 임산부 정보가 들어가는지 확인한다."""
    example_patient["remark"] = "3층 높이에서 추락"
    example_patient["specialInfo"]["pregnancyInfo"] = {"weeks": 24}

    data = patient_assessment.build_input(Patient.model_validate(example_patient))

    assert data["remark"] == "3층 높이에서 추락"
    assert data["pregnancy_info"] == {"weeks": 24}


def test_trauma_criteria_groups_cover_all_criteria():
    """중증외상 기준 항목마다 분류(신체검사 소견, 손상기전, 특수상황)가 정확히 하나인지 확인한다.

    분류가 없는 항목은 프롬프트의 값 목록에 나오지 않고 판정에도 쓰이지 않는다.
    """
    assert INJURY_FINDINGS | INJURY_MECHANISMS | SPECIAL_SITUATIONS == set(TraumaCriterion)
    assert len(INJURY_FINDINGS) + len(INJURY_MECHANISMS) + len(SPECIAL_SITUATIONS) == len(TraumaCriterion)


@pytest.mark.parametrize("failure", list(LlmFailure))
def test_failure_returns_none_with_warning(example_patient, failure):
    """LlmClient가 실패 사유를 반환하면 결과 없음(None)과 "환자 상태 판단 실패" 경고가 나오는지 확인한다."""
    warnings: list[WarningCode] = []

    result = patient_assessment.assess(Patient.model_validate(example_patient), FakeLlmClient(failure), warnings)

    assert result is None
    assert warnings == [WarningCode.ASSESSMENT_FAILED]


def test_success_returns_parsed_output(example_patient):
    """LlmClient가 정상 출력을 반환하면 파싱한 출력을 그대로 반환하고 경고를 추가하지 않는지 확인한다.

    LlmClient에는 출력 모델 PatientAssessment와 환자 상태 판단 제한 시간을 넘긴다.
    """
    client = FakeLlmClient(LlmOutput(parsed=OPEN_FRACTURE, raw=OPEN_FRACTURE.model_dump_json()))
    warnings: list[WarningCode] = []
    patient = Patient.model_validate(example_patient)

    result = patient_assessment.assess(patient, client, warnings)

    assert result == OPEN_FRACTURE
    assert warnings == []
    [call] = client.calls
    assert call.messages == patient_assessment.build_messages(patient)
    assert call.response_format is PatientAssessment
    assert call.timeout == settings.assessment_timeout_seconds


@pytest.mark.parametrize(
    "output",
    [
        {"required_depts": ["순환기내과"]},
        {"supportive_depts": ["혈관외과"]},
        {"severe_disease_code": "mkioskty28"},
        {"trauma_criteria": ["위험한 나이"]},
    ],
    ids=["unknown-required-dept", "unknown-supportive-dept", "unknown-severe-disease-code", "risky-age-criterion"],
)
def test_output_model_rejects_values_outside_lists(output):
    """출력 모델이 진료과, 중증응급질환 코드, 중증외상 기준 항목 목록에 없는 값을 거부하는지 확인한다.

    위험한 나이는 시스템이 나이로 판정하므로 중증외상 기준 항목 목록에 없다.
    """
    valid = {
        "is_trauma": True,
        "required_depts": [],
        "supportive_depts": [],
        "severe_disease_code": None,
        "trauma_criteria": [],
    }

    with pytest.raises(ValidationError):
        PatientAssessment.model_validate({**valid, **output})
