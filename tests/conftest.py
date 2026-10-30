import json
from pathlib import Path

import pytest
from fake_hospital_repository import FakeHospitalRepository, default_repository
from fake_llm import FakeLlmClient
from fastapi.testclient import TestClient

from aimp.api.routes import get_hospital_repository, get_llm_client
from aimp.ports.llm import LlmFailure
from aimp.main import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def example_request() -> dict:
    """interface.md '병원 추천 요청'의 예시 요청 본문. 테스트마다 새로 읽는다."""
    return json.loads((FIXTURES / "example_request.json").read_text(encoding="utf-8"))


@pytest.fixture
def example_patient(example_request) -> dict:
    """예시 요청 본문의 patient 객체. 바꾸면 example_request에도 반영된다."""
    return example_request["patient"]


@pytest.fixture
def hospital_repository() -> FakeHospitalRepository:
    """client가 쓰는 가짜 HospitalRepository. 테스트가 hospitals를 바꿀 수 있다."""
    return default_repository()


@pytest.fixture
def client(hospital_repository):
    # 요청 검증 테스트가 vLLM과 병원정보 검색 API를 호출하지 않도록 가짜 구현을 쓴다.
    # 가짜 LlmClient는 LLM 호출 실패를 돌려준다.
    app.dependency_overrides[get_llm_client] = lambda: FakeLlmClient(LlmFailure.CALL_FAILED)
    app.dependency_overrides[get_hospital_repository] = lambda: hospital_repository
    yield TestClient(app)
    app.dependency_overrides.clear()
