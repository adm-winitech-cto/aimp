"""정적 병원 목록으로 하는 병원 선정 테스트."""

import random

import pytest
from fake_llm import FakeLlmClient

from transfer_recommender.api.request import RecommendRequest
from transfer_recommender.llm_client import LlmFailure, LlmOutput
from transfer_recommender.selection import static_selection
from transfer_recommender.selection.static_hospitals import GENERAL_HOSPITALS, HOSPITALS_BY_GROUP, DiseaseGroup
from transfer_recommender.selection.static_selection import StaticRecommendation, StaticSelection
from transfer_recommender.settings import settings

GENERAL_IDS = {hospital.hospital_id for hospital in GENERAL_HOSPITALS}


def _output(groups: tuple[DiseaseGroup, ...], *hospital_ids: str) -> LlmOutput:
    parsed = StaticSelection(
        disease_groups=groups,
        recommendations=tuple(StaticRecommendation(hospital_id=h, reason=f"근거 {h}") for h in hospital_ids),
    )
    return LlmOutput(parsed=parsed, raw=parsed.model_dump_json())


def _recommend(body: dict, result: LlmOutput | LlmFailure, seed: int = 0):
    client = FakeLlmClient(result)
    response = static_selection.recommend(RecommendRequest.model_validate(body), client, random.Random(seed))
    return response, client


def test_llm_recommendations_are_returned_in_order(example_request):
    """LLM이 고른 병원을 그 순서대로 1순위부터 반환하고, 병원명은 병원 목록에서 채우는지 확인한다."""
    response, _ = _recommend(example_request, _output((DiseaseGroup.SEVERE_TRAUMA,), "31100295", "31100759"))

    assert response.incident_id == "INC-20260831-000123"
    assert response.request_seq == 2
    assert [(r.rank, r.hospital_id, r.hospital_name, r.reason) for r in response.recommendations] == [
        (1, "31100295", "가톨릭대학교의정부성모병원", "근거 31100295"),
        (2, "31100759", "국군수도병원", "근거 31100759"),
    ]


def test_recommend_count_truncates(example_request):
    """recommendCount보다 많이 고르면 앞에서부터 recommendCount개만 반환하는지 확인한다."""
    example_request["recommendCount"] = 1

    response, _ = _recommend(example_request, _output((DiseaseGroup.SEVERE_TRAUMA,), "31100295", "31100759"))

    assert [r.hospital_id for r in response.recommendations] == ["31100295"]


def test_duplicate_and_rejected_hospitals_are_removed(example_request):
    """같은 병원은 한 번만 넣고, rejectedHospitals에 있는 병원은 빼고 순위를 다시 매기는지 확인한다."""
    example_request["rejectedHospitals"][0]["hospitalName"] = "국군수도병원"

    response, _ = _recommend(
        example_request, _output((DiseaseGroup.SEVERE_TRAUMA,), "31100295", "31100295", "31100759", "31100473")
    )

    assert [(r.rank, r.hospital_id) for r in response.recommendations] == [(1, "31100295"), (2, "31100473")]


@pytest.mark.parametrize(
    ("result", "reason"),
    [(_output(()), static_selection.FALLBACK_REASON), (LlmFailure.TIMEOUT, static_selection.LLM_FAILURE_REASON)],
    ids=["no-disease-group", "llm-failure"],
)
def test_empty_result_falls_back_to_random_general_hospitals(example_request, result, reason):
    """LLM이 빈 목록을 내거나 실패하면 일반 병원 목록에서 recommendCount개를 무작위로 고르고,
    추천 근거에 무작위로 고른 이유를 적는지 확인한다."""
    example_request["recommendCount"] = None

    response, _ = _recommend(example_request, result)

    ids = [r.hospital_id for r in response.recommendations]
    assert len(ids) == settings.recommend_count
    assert len(set(ids)) == len(ids)
    assert set(ids) <= GENERAL_IDS
    assert [r.rank for r in response.recommendations] == list(range(1, len(ids) + 1))
    assert all(r.reason == reason for r in response.recommendations)


def test_fallback_is_random(example_request):
    """무작위 선택이 난수 시드에 따라 달라지는지 확인한다."""
    first, _ = _recommend(example_request, _output(()), seed=1)
    second, _ = _recommend(example_request, _output(()), seed=2)

    assert first.recommendations != second.recommendations


def test_fallback_when_all_recommendations_rejected(example_request):
    """LLM이 고른 병원이 모두 거절된 병원이면 일반 병원 목록에서 고르고, 거절된 병원은 빼는지 확인한다."""
    example_request["recommendCount"] = 20
    example_request["rejectedHospitals"][0]["hospitalName"] = "국군수도병원"
    example_request["rejectedHospitals"].append(
        {"hospitalName": "아주대학교병원", "reason": None, "rejectedAt": "2026-08-31 17:21:00"}
    )

    response, _ = _recommend(example_request, _output((DiseaseGroup.SEVERE_TRAUMA,), "31100759"))

    names = {r.hospital_name for r in response.recommendations}
    assert len(names) == len(GENERAL_HOSPITALS) - 1
    assert "아주대학교병원" not in names


def test_llm_call_uses_output_model_and_timeout(example_request):
    """LLM 호출에 출력 모델 StaticSelection과 최종 선정 제한 시간을 넘기고, user 메시지에 4대 중증 구분을 넣는지 확인한다."""
    example_request["patient"]["majorSevereType"] = "심정지"

    _, client = _recommend(example_request, _output(()))

    [call] = client.calls
    assert call.response_format is StaticSelection
    assert call.timeout == settings.llm_timeout_seconds
    assert '"major_severe_type": "심정지"' in call.messages[1]["content"]


def test_output_schema_limits_hospital_ids_to_group_hospitals():
    """출력 스키마의 병원 ID 값 목록이 질환군 병원 목록의 ID와 같은지 확인한다. 일반 병원 목록만의 병원은 고를 수 없다."""
    schema = StaticSelection.model_json_schema()
    group_ids = {h.hospital_id for hospitals in HOSPITALS_BY_GROUP.values() for h in hospitals}

    assert set(schema["$defs"]["HospitalId"]["enum"]) == group_ids


def test_system_prompt_contains_goal_and_hospital_tables():
    """시스템 프롬프트에 목표 문장과 질환군별 병원 목록이 들어가는지 확인한다."""
    prompt = static_selection.SYSTEM_PROMPT

    assert "빠르게 일상에 복귀" in prompt
    for group in DiseaseGroup:
        assert f"## {group}" in prompt
    assert "- 31100759, 국군수도병원, 3건" in prompt
