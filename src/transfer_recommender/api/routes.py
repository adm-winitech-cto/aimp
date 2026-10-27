"""병원 추천 API 라우트."""

from fastapi import APIRouter, HTTPException, status

from transfer_recommender.api.request import RecommendRequest
from transfer_recommender.api.response import RecommendResponse

RECOMMEND_PATH = "/api/v1/recHosp"

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    # 프로세스가 요청에 응답하는지만 확인한다. DB와 vLLM 연결은 확인하지 않는다.
    return {"status": "ok"}


@router.post(RECOMMEND_PATH)
def recommend(body: RecommendRequest) -> RecommendResponse:
    # 처리 파이프라인은 '처리 파이프라인과 전체 흐름' 일감에서 연결한다.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "추천 처리는 아직 구현되지 않았습니다")
