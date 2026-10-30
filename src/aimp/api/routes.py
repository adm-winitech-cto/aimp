"""병원 추천 API 라우트."""

import random
from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends

from aimp import pipeline
from aimp.api.request import RecommendRequest
from aimp.api.response import Recommendation, RecommendResponse
from aimp.adapters.vllm import VllmClient
from aimp.ports.llm import LlmClient

RECOMMEND_PATH = "/api/v1/recHosp"

router = APIRouter()


@cache
def get_llm_client() -> LlmClient:
    return VllmClient()


def get_rng() -> random.Random:
    return random.Random()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    # 프로세스가 요청에 응답하는지만 확인한다. DB와 vLLM 연결은 확인하지 않는다.
    return {"status": "ok"}


@router.post(RECOMMEND_PATH)
def recommend(
    body: RecommendRequest,
    llm_client: Annotated[LlmClient, Depends(get_llm_client)],
    rng: Annotated[random.Random, Depends(get_rng)],
) -> RecommendResponse:
    result = pipeline.run(body, llm_client, rng)
    return RecommendResponse(
        incident_id=body.incident_id,
        request_seq=body.request_seq,
        recommendations=[
            Recommendation(hospital_id=h.hospital_id, hospital_name=h.hospital_name, rank=rank, reason=h.reason)
            for rank, h in enumerate(result.recommendations, start=1)
        ],
    )
