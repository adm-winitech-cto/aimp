"""처리 흐름 테스트."""

import random

import pytest
from fake_llm import FakeLlmClient

from aimp import pipeline
from aimp.api.request import RecommendRequest
from aimp.api.routes import RECOMMEND_PATH
from aimp.domain.types import PatientCategory, Resource, WarningCode
from aimp.ports.llm import LlmFailure


def _run(body: dict) -> pipeline.PipelineResult:
    return pipeline.run(RecommendRequest.model_validate(body), FakeLlmClient(LlmFailure.CALL_FAILED), random.Random(0))


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
