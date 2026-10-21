"""interface.md '필수 여부 규칙'에 따른 요청 검증 응답 테스트."""

import json
import logging

import pytest

from transfer_recommender.api.routes import RECOMMEND_PATH
from transfer_recommender.main import MAX_LOGGED_BODY_BYTES

REQUIRED_KEYS = [
    ("patientInfo",),
    ("patientInfo", "age"),
    ("consciousnessLevel",),
    ("preKtas",),
    ("preKtas", "level"),
    ("preKtas", "assessmentDetail"),
    ("vitalSigns", 0, "recordedAt"),
    ("medicalHistory", 0, "diseaseName"),
    ("specialPatientInfo",),
    ("specialPatientInfo", "pregnancyInfo"),
    ("specialPatientInfo", "newbornInfo"),
    ("patientLocation",),
    ("patientLocation", "longitude"),
    ("patientLocation", "latitude"),
]

NON_NULLABLE = [
    # 필수 필드
    ("patientInfo",),
    ("patientInfo", "age"),
    ("consciousnessLevel",),
    ("preKtas",),
    ("preKtas", "level"),
    ("preKtas", "assessmentDetail"),
    ("vitalSigns", 0, "recordedAt"),
    ("medicalHistory", 0, "diseaseName"),
    ("specialPatientInfo",),
    ("patientLocation",),
    ("patientLocation", "longitude"),
    ("patientLocation", "latitude"),
    # optional이지만 '생략 시 처리'가 null이 아닌 필드
    ("symptoms",),
    ("vitalSigns",),
    ("medicalHistory",),
    ("medications",),
    ("preKtas", "assessmentRound"),
]

NULLABLE = [
    ("patientInfo", "sex"),
    ("patientInfo", "patientType"),
    ("chiefComplaint",),
    ("majorSevereType",),
    ("vitalSigns", 0, "measuredAt"),
    ("vitalSigns", 0, "systolicBpMmHg"),
    ("vitalSigns", 0, "spo2Percent"),
    ("medicalHistory", 0, "detail"),
    ("specialPatientInfo", "pregnancyInfo"),
    ("specialPatientInfo", "newbornInfo"),
    ("remark",),
    ("requestCnt",),
]


def _path_id(path):
    return ".".join(str(key) for key in path)


def _parent(body, path):
    for key in path[:-1]:
        body = body[key]
    return body


def test_healthz_returns_ok(client):
    """/healthz가 200과 {"status": "ok"}를 반환하는지 확인한다."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_request_passes_validation(client, example_request):
    """interface.md 예시 요청이 요청 검증을 통과하는지 확인한다."""
    # 검증을 통과하면 처리 파이프라인이 연결되기 전까지 501을 반환한다.
    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 501


@pytest.mark.parametrize("path", REQUIRED_KEYS, ids=_path_id)
def test_missing_required_key_returns_400(client, example_request, path):
    """필수 키를 하나씩 빼면 400을 반환하고, 오류의 loc가 빠진 키를 가리키는지 확인한다."""
    del _parent(example_request, path)[path[-1]]

    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 400
    assert ["body", *path] in [error["loc"] for error in response.json()["detail"]]


@pytest.mark.parametrize("path", NON_NULLABLE, ids=_path_id)
def test_null_on_non_nullable_field_returns_400(client, example_request, path):
    """null을 받지 않는 필드에 null을 넣으면 400을 반환하는지 확인한다."""
    _parent(example_request, path)[path[-1]] = None

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 400


@pytest.mark.parametrize("path", NULLABLE, ids=_path_id)
def test_null_on_nullable_field_passes_validation(client, example_request, path):
    """null을 받는 필드에 null을 넣으면 요청 검증을 통과하는지 확인한다."""
    _parent(example_request, path)[path[-1]] = None

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 501


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-31T17:11:26",
        "2026/08/31 17:11:26",
        "2026-8-31 7:1:2",
        "2026-08-31\t17:11:26",
        "2026-08-31  17:11:26",
        1788167486,
    ],
)
def test_invalid_recorded_at_returns_400(client, example_request, value):
    """recordedAt이 yyyy-MM-dd HH:mm:ss 형식의 문자열이 아니면 400을 반환하는지 확인한다."""
    example_request["vitalSigns"][0]["recordedAt"] = value

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 400


def test_invalid_timestamp_message_does_not_echo_input(client, example_request):
    """시각 형식 오류의 400 응답 메시지에 입력값이 들어가지 않는지 확인한다."""
    example_request["vitalSigns"][0]["measuredAt"] = "MARKER-환자정보"

    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 400
    assert "MARKER" not in response.text


@pytest.mark.parametrize("level", [0, 6])
def test_pre_ktas_level_out_of_range_returns_400(client, example_request, level):
    """Pre-KTAS 단계가 1~5 범위를 벗어나면 400을 반환하는지 확인한다."""
    example_request["preKtas"]["level"] = level

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 400


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("patientInfo", "age"), True),
        (("patientInfo", "age"), "65"),
        (("preKtas", "level"), True),
        (("vitalSigns", 0, "spo2Percent"), "97"),
        (("requestCnt",), True),
        (("requestCnt",), "2"),
    ],
    ids=lambda v: _path_id(v) if isinstance(v, tuple) else repr(v),
)
def test_non_number_on_number_field_returns_400(client, example_request, path, value):
    """숫자 필드에 불리언이나 문자열이 오면 숫자로 바꾸지 않고 400을 반환하는지 확인한다."""
    _parent(example_request, path)[path[-1]] = value

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 400


@pytest.mark.parametrize("value", [0, -1])
def test_request_cnt_below_1_returns_400(client, example_request, value):
    """추천받을 병원 수(requestCnt)가 1보다 작으면 400을 반환하는지 확인한다."""
    example_request["requestCnt"] = value

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 400


def test_fraction_on_integer_field_returns_400(client, example_request):
    """정수 필드(requestCnt)에 소수가 오면 정수로 바꾸지 않고 400을 반환하는지 확인한다."""
    example_request["requestCnt"] = 1.5

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 400


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=repr)
def test_non_finite_number_returns_400(client, example_request, value):
    """숫자 필드에 NaN, Infinity, -Infinity가 오면 400을 반환하는지 확인한다."""
    example_request["vitalSigns"][0]["spo2Percent"] = value

    # json.dumps는 NaN, Infinity를 JSON 표준 밖의 토큰 그대로 쓴다. 클라이언트가 이런 본문을 보내는 경우를 흉내 낸다.
    response = client.post(RECOMMEND_PATH, content=json.dumps(example_request), headers={"Content-Type": "application/json"})

    assert response.status_code == 400


@pytest.mark.parametrize("value", ["심정지", "중증외상", "뇌졸중", "심근경색"])
def test_major_severe_type_values_pass_validation(client, example_request, value):
    """majorSevereType에 4대 중증 4종이 오면 요청 검증을 통과하는지 확인한다."""
    example_request["majorSevereType"] = value

    assert client.post(RECOMMEND_PATH, json=example_request).status_code == 501


@pytest.mark.parametrize("value", ["없음", "심정지 ", ""])
def test_unknown_major_severe_type_returns_400(client, example_request, value):
    """majorSevereType에 4대 중증 4종이 아닌 값(공백이 붙은 값 포함)이 오면 무시하지 않고 400을 반환하는지 확인한다."""
    example_request["majorSevereType"] = value

    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 400
    assert response.json()["detail"][0]["loc"] == ["body", "majorSevereType"]


def test_unknown_key_returns_400(client, example_request):
    """명세에 없는 키(예: camelCase가 아닌 vital_signs)가 오면 기본값으로 넘어가지 않고 400을 반환하는지 확인한다."""
    example_request["vital_signs"] = example_request.pop("vitalSigns")

    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.status_code == 400
    assert {"loc": ["body", "vital_signs"], "msg": "Extra inputs are not permitted", "type": "extra_forbidden"} in response.json()["detail"]


def test_deeply_nested_body_returns_400(client):
    """아주 깊게 중첩된 JSON 본문에 500이 아니라 400을 반환하는지 확인한다."""
    response = client.post(RECOMMEND_PATH, content="[" * 100_000, headers={"Content-Type": "application/json"})

    assert response.status_code == 400


def test_400_response_does_not_echo_request_body(client, example_request):
    """400 응답이 요청 본문(input)을 되돌려 주지 않고 loc, msg, type만 담는지 확인한다."""
    del example_request["specialPatientInfo"]

    response = client.post(RECOMMEND_PATH, json=example_request)

    assert response.json() == {
        "detail": [{"loc": ["body", "specialPatientInfo"], "msg": "Field required", "type": "missing"}]
    }


def _body_log(caplog):
    return next(r.getMessage() for r in caplog.records if r.getMessage().startswith("요청 본문"))


def test_request_body_is_logged_in_one_line(client, example_request, caplog):
    """줄바꿈이 있는 요청 본문을 repr로 이스케이프해 INFO 로그 한 줄에 그대로 남기는지 확인한다."""
    pretty = json.dumps(example_request, ensure_ascii=False, indent=4)

    with caplog.at_level(logging.INFO, logger="transfer_recommender.main"):
        client.post(RECOMMEND_PATH, content=pretty, headers={"Content-Type": "application/json"})

    message = _body_log(caplog)
    assert "\n" not in message
    assert message.endswith(f"body={pretty!r}")


def test_large_request_body_is_truncated_in_log(client, caplog):
    """MAX_LOGGED_BODY_BYTES보다 큰 본문은 앞부분만 로그에 남기는지 확인한다."""
    body = '{"remark": "' + "x" * MAX_LOGGED_BODY_BYTES + '"}'

    with caplog.at_level(logging.INFO, logger="transfer_recommender.main"):
        client.post(RECOMMEND_PATH, content=body, headers={"Content-Type": "application/json"})

    assert _body_log(caplog).endswith(f"body={body[:MAX_LOGGED_BODY_BYTES]!r}")


def test_invalid_request_body_is_logged_with_errors(client, example_request, caplog):
    """요청 검증에 실패한 요청도 본문과 검증 실패 내용(오류 위치, 종류)을 함께 로그에 남기는지 확인한다."""
    del example_request["specialPatientInfo"]

    with caplog.at_level(logging.INFO, logger="transfer_recommender.main"):
        client.post(RECOMMEND_PATH, json=example_request)

    assert "자유서술" in caplog.text
    assert "errors=body.specialPatientInfo:missing" in caplog.text


def test_request_without_body_logs_no_body(client, caplog):
    """본문이 없는 GET /healthz 요청에는 요청 본문 로그를 남기지 않는지 확인한다."""
    with caplog.at_level(logging.INFO, logger="transfer_recommender.main"):
        client.get("/healthz")

    assert "요청 본문" not in caplog.text


def test_malformed_json_returns_400(client):
    """JSON 문법이 깨진 요청 본문에 FastAPI 기본값인 422 대신 400을 반환하는지 확인한다."""
    response = client.post(RECOMMEND_PATH, content="{", headers={"Content-Type": "application/json"})

    assert response.status_code == 400
