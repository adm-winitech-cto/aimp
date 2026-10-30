"""처리 흐름 테스트."""

import random

import pytest
from fake_llm import FakeLlmClient

from aimp import pipeline
from aimp.api.request import RecommendRequest
from aimp.api.routes import RECOMMEND_PATH
from aimp.classification import severity
from aimp.domain.patient import PatientAssessment
from aimp.domain.types import Department, PatientCategory, Resource, WarningCode
from aimp.ports.llm import LlmFailure, LlmOutput

# 발등 개방성 골절 예시를 "외상, 정형외과 필수"로 판단한 환자 상태 판단 결과
OPEN_FRACTURE = PatientAssessment(
    is_trauma=True,
    required_depts=(Department.ORTHOPEDIC_SURGERY,),
    supportive_depts=(),
    severe_disease_code=None,
    trauma_criteria=(),
)


def _run(body: dict, llm_client: FakeLlmClient | None = None) -> pipeline.PipelineResult:
    # 임시 선정 단계의 LLM 호출은 실패시켜, 일반 병원 목록에서 무작위로 고르게 한다.
    llm_client = llm_client or FakeLlmClient(LlmFailure.CALL_FAILED)
    return pipeline.run(RecommendRequest.model_validate(body), llm_client, random.Random(0))


def test_example_request_is_recommended_through_pipeline(client, example_request):
    """예시 요청을 보내면 pipeline.py를 거쳐 200과 recommendCount개 이하의 추천 병원을 1순위부터 반환하는지 확인한다."""
    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 200
    body = response.json()
    assert body["incidentId"] == example_request["incidentId"]
    assert body["requestSeq"] == example_request["requestSeq"]
    ranks = [r["rank"] for r in body["recommendations"]]
    assert 0 < len(ranks) <= example_request["recommendCount"]
    assert ranks == list(range(1, len(ranks) + 1))


def test_major_severe_type_sets_category(example_request, example_patient):
    """4대 중증 구분이 중증외상이면 A0이 적용 규칙을 중증외상으로 정하는지 확인한다."""
    example_patient["majorSevereType"] = "중증외상"

    assert _run(example_request).severe_judgment.category == PatientCategory.SEVERE_TRAUMA


def test_child_needs_pediatric_emergency(example_request, example_patient):
    """15세 미만 환자에게 A0이 특수 자원 '소아 응급 진료'를 붙이는지 확인한다."""
    example_patient["info"]["age"] = 7

    assert Resource.PEDIATRIC_EMERGENCY in _run(example_request).severe_judgment.required_resources


@pytest.mark.parametrize("missing", [True, False], ids=["missing", "present"])
def test_no_vital_signs_warning_for_major_severe_patient(example_request, example_patient, missing):
    """4대 중증 환자도 활력징후가 없으면 "활력징후 없음" 경고를 받고, 활력징후가 있으면 받지 않는지 확인한다."""
    example_patient["majorSevereType"] = "심근경색"
    if missing:
        example_patient["vitalSigns"] = None

    assert (WarningCode.NO_VITAL_SIGNS in _run(example_request).warnings) is missing


def test_assessment_is_kept_in_result(example_request):
    """환자 상태 판단 LLM이 정상 출력을 주면, 그 판단 결과가 결과 객체에 있고 경고가 없는지 확인한다."""
    output = LlmOutput(parsed=OPEN_FRACTURE, raw=OPEN_FRACTURE.model_dump_json())
    llm_client = FakeLlmClient(LlmFailure.CALL_FAILED, results_by_format={PatientAssessment: output})

    result = _run(example_request, llm_client)

    assert result.assessment == OPEN_FRACTURE
    assert WarningCode.ASSESSMENT_FAILED not in result.warnings


def test_assessment_failure_does_not_fail_request(client, example_request):
    """환자 상태 판단 LLM이 실패해도 요청을 실패로 처리하지 않고, 경고를 넣은 뒤 다음 단계로 넘어가는지 확인한다."""
    result = _run(example_request)

    assert result.assessment is None
    assert WarningCode.ASSESSMENT_FAILED in result.warnings
    assert result.recommendations
    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 200


def test_major_severe_patient_skips_severity_judgment(example_request, example_patient, monkeypatch):
    """4대 중증 환자에게는 중증도 판정(A2)을 호출하지 않고 A0이 정한 적용 규칙을 쓰는지 확인한다."""
    example_patient["majorSevereType"] = "중증외상"

    def fail(*args):
        raise AssertionError("4대 중증 환자에게 severity.judge를 호출했다")

    monkeypatch.setattr(severity, "judge", fail)

    assert _run(example_request).category == PatientCategory.SEVERE_TRAUMA


def test_open_fracture_example_is_minor_trauma_with_risky_age(example_request):
    """발등 개방성 골절 예시(65세)가 "외상, 정형외과 필수"로 판단되면, 적용 규칙이 경증외상이고
    특수상황 항목에 위험한 나이가 있는지 확인한다."""
    output = LlmOutput(parsed=OPEN_FRACTURE, raw=OPEN_FRACTURE.model_dump_json())
    llm_client = FakeLlmClient(LlmFailure.CALL_FAILED, results_by_format={PatientAssessment: output})

    result = _run(example_request, llm_client)

    assert result.category == PatientCategory.MINOR_TRAUMA
    assert result.special_situations == (severity.RISKY_AGE,)


def test_major_severe_trauma_patient_gets_special_situations(example_request, example_patient):
    """4대 중증 구분이 중증외상인 55세 이상 환자도 특수상황 판정을 받아 위험한 나이 항목이 있는지 확인한다."""
    example_patient["majorSevereType"] = "중증외상"
    example_patient["info"]["age"] = 55

    assert severity.RISKY_AGE in _run(example_request).special_situations
