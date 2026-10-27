import json
from pathlib import Path

import pytest
from fake_llm import FakeLlmClient
from fastapi.testclient import TestClient

from transfer_recommender.api.routes import get_llm_client
from transfer_recommender.llm_client import LlmFailure
from transfer_recommender.main import app

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
def client():
    # 요청 검증 테스트가 vLLM을 호출하지 않도록 LLM 호출 실패를 돌려주는 가짜 LlmClient를 쓴다.
    app.dependency_overrides[get_llm_client] = lambda: FakeLlmClient(LlmFailure.CALL_FAILED)
    yield TestClient(app)
    app.dependency_overrides.clear()
