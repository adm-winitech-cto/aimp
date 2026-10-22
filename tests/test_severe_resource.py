"""중증·특수 자원 판단(A0) 테스트. design.md '판정 규칙' 표의 행마다 확인한다."""

import pytest

from transfer_recommender.api.request import RecommendRequest
from transfer_recommender.classification import severe_resource
from transfer_recommender.domain.patient import SevereJudgment
from transfer_recommender.domain.types import PatientCategory, Resource, SevereType


def _judge(body: dict) -> SevereJudgment:
    return severe_resource.judge(RecommendRequest.model_validate(body))


@pytest.mark.parametrize(
    ("severe_type", "category", "resources"),
    [
        ("심정지", PatientCategory.CARDIAC_ARREST, set()),
        ("중증외상", PatientCategory.SEVERE_TRAUMA, set()),
        ("뇌졸중", PatientCategory.STROKE_SUSPECTED, {Resource.STROKE_TREATMENT}),
        ("심근경색", PatientCategory.SEVERE_NON_TRAUMA, {Resource.MI_REPERFUSION}),
    ],
)
def test_major_severe_type_sets_category_and_resources(example_request, severe_type, category, resources):
    """4대 중증 구분마다 '판정 규칙' 표의 적용 규칙과 특수 자원이 나오는지 확인한다. 뇌졸중은 '뇌졸중 의증' 규칙을 적용한다."""
    example_request["majorSevereType"] = severe_type

    judgment = _judge(example_request)

    assert judgment.severe_type == SevereType(severe_type)
    assert judgment.category == category
    assert judgment.required_resources == resources


def test_no_major_severe_type_leaves_category_empty(example_request):
    """4대 중증이 아니고 소아·임산부도 아니면 적용 규칙과 특수 자원이 모두 비는지 확인한다."""
    assert _judge(example_request) == SevereJudgment(severe_type=None, category=None, required_resources=frozenset())


@pytest.mark.parametrize(("age", "pediatric"), [(0.5, True), (14.9, True), (15, False)])
def test_under_15_requires_pediatric_emergency(example_request, age, pediatric):
    """15세 미만이면 소아 응급 진료 자원이 필요하고, 적용 규칙은 바꾸지 않는지 확인한다."""
    example_request["patientInfo"]["age"] = age

    judgment = _judge(example_request)

    assert (Resource.PEDIATRIC_EMERGENCY in judgment.required_resources) is pediatric
    assert judgment.category is None


def test_pregnancy_info_requires_delivery(example_request):
    """임산부정보 값이 있으면 분만 자원이 필요한지 확인한다. 객체 구조가 미정이라 빈 객체로 값이 있는 경우를 나타낸다."""
    example_request["specialPatientInfo"]["pregnancyInfo"] = {}

    judgment = _judge(example_request)

    assert judgment.required_resources == {Resource.DELIVERY}
    assert judgment.category is None


def test_newborn_info_is_not_used(example_request):
    """신생아정보 값이 있어도 특수 자원이 추가되지 않는지 확인한다."""
    example_request["specialPatientInfo"]["newbornInfo"] = {}

    assert _judge(example_request).required_resources == set()


def test_pregnant_stroke_patient_requires_two_resources(example_request):
    """임산부 뇌졸중 환자에게 뇌졸중 치료 자원과 분만 자원이 함께 필요한지 확인한다."""
    example_request["majorSevereType"] = "뇌졸중"
    example_request["specialPatientInfo"]["pregnancyInfo"] = {}

    judgment = _judge(example_request)

    assert judgment.category == PatientCategory.STROKE_SUSPECTED
    assert judgment.required_resources == {Resource.STROKE_TREATMENT, Resource.DELIVERY}
