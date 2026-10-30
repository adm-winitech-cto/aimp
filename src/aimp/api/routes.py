"""병원 추천 API 라우트."""

from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends

from aimp import pipeline
from aimp.api.request import RecommendRequest
from aimp.api.response import Recommendation, RecommendResponse
from aimp.adapters.hospital_api import HospitalApiRepository
from aimp.adapters.tmap_eta import TmapEtaProvider
from aimp.adapters.vllm import VllmClient
from aimp.ports.eta_provider import EtaProvider
from aimp.ports.hospital_repository import HospitalRepository
from aimp.ports.llm import LlmClient

RECOMMEND_PATH = "/api/v1/recHosp"

router = APIRouter()


@cache
def get_llm_client() -> LlmClient:
    return VllmClient()


@cache
def get_hospital_repository() -> HospitalRepository:
    return HospitalApiRepository()


@cache
def get_eta_provider() -> EtaProvider:
    return TmapEtaProvider()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    # 프로세스가 요청에 응답하는지만 확인한다. DB와 vLLM 연결은 확인하지 않는다.
    return {"status": "ok"}


@router.post(RECOMMEND_PATH)
def recommend(
    body: RecommendRequest,
    llm_client: Annotated[LlmClient, Depends(get_llm_client)],
    hospital_repository: Annotated[HospitalRepository, Depends(get_hospital_repository)],
    eta_provider: Annotated[EtaProvider, Depends(get_eta_provider)],
) -> RecommendResponse:
    result = pipeline.run(body, llm_client, hospital_repository, eta_provider)
    return RecommendResponse(
        incident_id=body.incident_id,
        request_seq=body.request_seq,
        recommendations=[
            Recommendation(hospital_id=h.hospital_id, hospital_name=h.hospital_name, rank=rank, reason=h.reason)
            for rank, h in enumerate(result.recommendations, start=1)
        ],
    )
