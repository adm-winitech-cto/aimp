"""병원 추천 API 라우트."""

import random
from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends

from aimp.api.request import RecommendRequest
from aimp.api.response import RecommendResponse
from aimp.adapters.vllm import VllmClient
from aimp.ports.llm import LlmClient
from aimp.selection import static_selection

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
    # 처리 파이프라인을 구현하기 전까지 정적 병원 목록으로 선정한다.
    return static_selection.recommend(body, llm_client, rng)
