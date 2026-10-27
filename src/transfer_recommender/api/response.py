"""병원 추천 응답 스키마. interface.md '병원 추천 응답'의 필드 표를 그대로 옮겼다."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _ResponseModel(BaseModel):
    # JSON 필드명은 camelCase, 파이썬 속성명은 snake_case
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Recommendation(_ResponseModel):
    hospital_id: str
    hospital_name: str
    rank: int
    reason: str


class RecommendResponse(_ResponseModel):
    incident_id: str
    request_seq: int
    recommendations: list[Recommendation]  # rank 오름차순, 최대 recommendCount개
