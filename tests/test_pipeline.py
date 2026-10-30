"""처리 흐름 테스트."""

import pytest
from fake_eta_provider import FakeEtaProvider
from fake_hospital_repository import FakeHospitalRepository, default_repository, make_hospital
from fake_llm import FakeLlmClient

from aimp import pipeline
from aimp.api.request import RecommendRequest
from aimp.api.routes import RECOMMEND_PATH
from aimp.classification import severity
from aimp.common.settings import settings
from aimp.domain.eta import EtaMethod
from aimp.domain.patient import PatientAssessment
from aimp.domain.recommendation import PipelineResult
from aimp.domain.types import Department, HospitalCategory, Level, PatientCategory, Resource, WarningCode
from aimp.ports.llm import LlmFailure, LlmOutput

# 발등 개방성 골절 예시를 "외상, 정형외과 필수"로 판단한 환자 상태 판단 결과
OPEN_FRACTURE = PatientAssessment(
    is_trauma=True,
    required_depts=(Department.ORTHOPEDIC_SURGERY,),
    supportive_depts=(),
    severe_disease_code=None,
    trauma_criteria=(),
)


def _open_fracture_llm() -> FakeLlmClient:
    return FakeLlmClient(LlmOutput(parsed=OPEN_FRACTURE, raw=OPEN_FRACTURE.model_dump_json()))


REC = HospitalCategory.REGIONAL_EMERGENCY_CENTER
LEC = HospitalCategory.LOCAL_EMERGENCY_CENTER
LEI = HospitalCategory.LOCAL_EMERGENCY_INSTITUTION
RTC = HospitalCategory.REGIONAL_TRAUMA_CENTER


def _run(
    body: dict,
    llm_client: FakeLlmClient | None = None,
    hospital_repository: FakeHospitalRepository | None = None,
    eta_provider: FakeEtaProvider | None = None,
) -> PipelineResult:
    """llm_client를 주지 않으면 환자 상태 판단이 실패하고, hospital_repository를 주지 않으면 default_repository()를,
    eta_provider를 주지 않으면 모든 병원의 ETA를 구하는 FakeEtaProvider()를 쓴다."""
    return pipeline.run(
        RecommendRequest.model_validate(body),
        llm_client or FakeLlmClient(LlmFailure.CALL_FAILED),
        hospital_repository or default_repository(),
        eta_provider or FakeEtaProvider(),
    )


def _ids(result: PipelineResult) -> list[str]:
    return [hospital.hospital_id for hospital in result.recommendations]


def test_example_request_is_recommended_through_pipeline(client, example_request, hospital_repository):
    """예시 요청을 보내면 pipeline.py를 거쳐 200을 반환하고, 추천 병원이 모두 가짜 HospitalRepository의 병원이고,
    순위가 1부터 매겨지는지 확인한다."""
    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 200
    body = response.json()
    assert body["incidentId"] == example_request["incidentId"]
    assert body["requestSeq"] == example_request["requestSeq"]
    recommendations = body["recommendations"]
    assert 0 < len(recommendations) <= example_request["recommendCount"]
    assert {r["hospitalId"] for r in recommendations} <= {h.hospital_id for h in hospital_repository.hospitals}
    assert [r["rank"] for r in recommendations] == list(range(1, len(recommendations) + 1))


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
    result = _run(example_request, _open_fracture_llm())

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
    result = _run(example_request, _open_fracture_llm())

    assert result.category == PatientCategory.MINOR_TRAUMA
    assert result.special_situations == (severity.RISKY_AGE,)


def test_major_severe_trauma_patient_gets_special_situations(example_request, example_patient):
    """4대 중증 구분이 중증외상인 55세 이상 환자도 특수상황 판정을 받아 위험한 나이 항목이 있는지 확인한다."""
    example_patient["majorSevereType"] = "중증외상"
    example_patient["info"]["age"] = 55

    assert severity.RISKY_AGE in _run(example_request).special_situations


def test_hospitals_are_looked_up_once_with_l0_and_l1_categories(example_request, example_patient):
    """적용 규칙이 비외상 중증이면, L0 조건(권역·지역응급의료센터)과 L1 조건(지역응급의료기관)의 병원 분류를
    합쳐 병원 데이터를 한 번만 조회하는지 확인한다."""
    example_patient["majorSevereType"] = "심근경색"  # 적용 규칙: 비외상 중증
    repository = default_repository()

    _run(example_request, hospital_repository=repository)

    assert repository.calls == [frozenset({REC, LEC, LEI})]


def test_l0_candidates_are_recommended_without_medical_direction(example_request, example_patient):
    """L0 조건을 만족하는 병원이 있으면 L0 조건의 병원만 추천하고 "의료지도 필요" 표시를 넣지 않는지 확인한다."""
    example_patient["majorSevereType"] = "심근경색"

    result = _run(example_request)

    assert _ids(result) == ["LEC", "REC"]
    assert result.level == Level.L0
    assert not result.medical_direction_needed


def test_l1_candidates_are_recommended_with_medical_direction(example_request, example_patient):
    """L0 조건을 만족하는 병원이 0곳이면 L1 조건의 병원을 추천하고 "의료지도 필요" 표시를 넣는지 확인한다."""
    example_patient["majorSevereType"] = "심근경색"
    repository = FakeHospitalRepository([make_hospital("LEI1", 1.5, LEI), make_hospital("LEI2", 4.2, LEI)])

    result = _run(example_request, hospital_repository=repository)

    assert _ids(result) == ["LEI1", "LEI2"]
    assert result.level == Level.L1
    assert result.medical_direction_needed


@pytest.mark.parametrize(
    ("major_severe_type", "llm_client"),
    [("심근경색", None), (None, _open_fracture_llm())],
    ids=["no-l1-candidates", "no-l1-condition"],
)
def test_no_candidates_returns_empty_recommendations(example_request, example_patient, major_severe_type, llm_client):
    """L1 조건으로도 후보 병원이 0곳이거나(비외상 중증), 적용 규칙에 L1 조건이 없고 L0 조건으로 후보 병원이
    0곳이면(경증외상) 빈 추천 목록을 반환하는지 확인한다."""
    example_patient["majorSevereType"] = major_severe_type
    repository = FakeHospitalRepository([make_hospital("RTC", 1.0, RTC)])

    result = _run(example_request, llm_client, repository)

    assert result.recommendations == ()
    assert result.level is None
    assert not result.medical_direction_needed


@pytest.mark.parametrize(
    ("recommend_count", "expected"),
    [(2, 2), (None, settings.recommend_count), (20, 12)],
    ids=["recommend-count", "default", "fewer-candidates"],
)
def test_nearest_n_candidates_are_recommended(example_request, example_patient, recommend_count, expected):
    """후보 병원 중 직선거리가 가까운 병원을 recommendCount개(null이면 recommend_count개) 추천하고,
    후보 병원이 그보다 적으면 모두 추천하는지 확인한다."""
    example_patient["majorSevereType"] = "심근경색"
    example_request["recommendCount"] = recommend_count
    repository = FakeHospitalRepository([make_hospital(f"H{i:02}", 20.0 - i, REC) for i in range(12)])

    result = _run(example_request, hospital_repository=repository)

    assert _ids(result) == [f"H{i:02}" for i in range(11, 11 - expected, -1)]
    assert result.recommendations[0].reason == "직선거리 9.0km"


def test_recommendations_come_from_nearest_m_candidates(example_request, example_patient):
    """레벨 조건을 통과한 후보 병원이 M개(llm_candidate_count)보다 많으면, recommendCount가 M보다 커도
    직선거리가 가까운 M개 안에서만 추천하는지 확인한다."""
    m = settings.llm_candidate_count
    example_patient["majorSevereType"] = "심근경색"
    example_request["recommendCount"] = m + 5
    repository = FakeHospitalRepository([make_hospital(f"H{i:02}", float(i + 1), REC) for i in range(m + 5)])

    result = _run(example_request, hospital_repository=repository)

    assert _ids(result) == [f"H{i:02}" for i in range(m)]


def test_eta_is_estimated_only_for_recommended_hospitals(example_request, example_patient):
    """ETA를 추천 병원 N개에만 구하고, 받은 병원과 순서가 추천 병원과 같은지 확인한다. ETA로 순위를 바꾸지 않는다."""
    example_patient["majorSevereType"] = "심근경색"
    example_request["recommendCount"] = 1
    eta_provider = FakeEtaProvider()

    result = _run(example_request, eta_provider=eta_provider)

    assert eta_provider.calls == [["LEC"]]
    assert [(h.hospital_id, h.eta.hospital_id) for h in result.recommendations] == [("LEC", "LEC")]


@pytest.mark.parametrize(("failing_ids", "warned"), [({"REC"}, True), (set(), False)], ids=["one-failed", "all-tmap"])
def test_eta_failure_warning(example_request, example_patient, failing_ids, warned):
    """병원 하나라도 ETA를 직선거리로 대신하면 "ETA 계산 실패(직선거리 대체)" 경고를 넣고,
    모두 Tmap ETA API로 구했으면 넣지 않는지 확인한다."""
    example_patient["majorSevereType"] = "심근경색"

    result = _run(example_request, eta_provider=FakeEtaProvider(frozenset(failing_ids)))

    methods = {h.hospital_id: h.eta.method for h in result.recommendations}
    assert methods == {"LEC": EtaMethod.TMAP, "REC": EtaMethod.STRAIGHT_LINE if warned else EtaMethod.TMAP}
    assert (WarningCode.ETA_FAILED in result.warnings) is warned


def test_eta_is_not_estimated_without_recommendations(example_request):
    """추천 병원이 0곳이면 EtaProvider를 호출하지 않는지 확인한다."""
    eta_provider = FakeEtaProvider()

    result = _run(example_request, hospital_repository=FakeHospitalRepository([]), eta_provider=eta_provider)

    assert result.recommendations == ()
    assert eta_provider.calls == []


def test_no_candidates_returns_200_with_empty_recommendations(client, example_request, hospital_repository):
    """L1 조건으로도 후보 병원이 0곳인 요청에 200과 빈 recommendations를 반환하는지 확인한다."""
    hospital_repository.hospitals = []

    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 200
    assert response.json()["recommendations"] == []
