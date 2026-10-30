"""앱 진입점(main.py)이 구현을 인터페이스에 연결하는지 확인하는 테스트."""

import pytest
from fastapi.testclient import TestClient

from aimp.adapters import hospital_api
from aimp.adapters.hospital_api import HospitalApiRepository
from aimp.adapters.tmap_eta import TmapEtaProvider
from aimp.adapters.vllm import VllmClient
from aimp.main import app


def test_lifespan_wires_implementations(monkeypatch, tmp_path):
    """앱이 시작할 때 vLLM, 병원정보 검색 API, Tmap ETA API 구현을 만들어 app.state에 두는지 확인한다.
    구현은 만들기만 하고 외부 시스템을 호출하지 않는다."""
    credentials = tmp_path / "client.json"
    credentials.write_text('{"clientId": "test-client", "apiKey": "test-key"}', encoding="utf-8")
    monkeypatch.setattr(hospital_api, "CREDENTIALS_PATH", credentials)

    with TestClient(app):
        assert isinstance(app.state.llm_client, VllmClient)
        assert isinstance(app.state.hospital_repository, HospitalApiRepository)
        assert isinstance(app.state.eta_provider, TmapEtaProvider)


def test_app_does_not_start_without_hospital_api_credentials(monkeypatch, tmp_path):
    """병원정보 검색 API 인증 파일(client.json)이 없으면 앱이 시작되지 않는지 확인한다."""
    monkeypatch.setattr(hospital_api, "CREDENTIALS_PATH", tmp_path / "client.json")

    with pytest.raises(ValueError, match="인증 파일이 없습니다"):
        with TestClient(app):
            pass
