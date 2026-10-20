import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from transfer_recommender.main import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def example_request() -> dict:
    """interface.md '병원 추천 요청'의 예시 요청 본문. 테스트마다 새로 읽는다."""
    return json.loads((FIXTURES / "example_request.json").read_text(encoding="utf-8"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
