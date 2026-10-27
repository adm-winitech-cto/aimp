"""정적 병원 목록으로 하는 병원 선정. 병원 데이터 조회와 후보 필터를 구현하기 전까지 쓰는 임시 선정 단계다.

- LLM이 환자 정보로 6대 중증질환 질환군을 판정하고, 질환군의 병원 목록에서 추천 병원을 고른다.
  병원 목록은 프롬프트에 넣는다. 출력 스키마의 병원 ID 값 목록을 질환군 병원으로 제한하므로 LLM은 목록 밖의 ID를 낼 수 없다.
- 후처리는 코드가 한다. 중복 병원과 거절된 병원을 빼고, 추천 병원 수만큼 자르고, 순위를 1부터 다시 매긴다.
- 추천 병원이 하나도 남지 않으면(질환군 미해당, 모두 거절, LLM 호출 실패) 일반 병원 목록에서 무작위로 고른다.
  LLM 호출이 실패했으면 추천 근거에 그 사실을 적는다.
"""

import json
import logging
import random
from enum import StrEnum
from pathlib import Path
from string import Template

from pydantic import BaseModel, ConfigDict

from transfer_recommender.api.request import RecommendRequest
from transfer_recommender.api.response import Recommendation, RecommendResponse
from transfer_recommender.classification.patient_assessment import build_input
from transfer_recommender.llm_client import ChatMessage, LlmClient, LlmFailure
from transfer_recommender.selection.static_hospitals import (
    GENERAL_HOSPITALS,
    GROUP_HOSPITAL_NAMES,
    HOSPITALS_BY_GROUP,
    DiseaseGroup,
)
from transfer_recommender.settings import settings

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "static_selection_v1.md"
FALLBACK_REASON = "6대 중증질환에 해당하지 않아 일반 이송 병원 목록에서 무작위로 골랐습니다."
LLM_FAILURE_REASON = "질환군을 판정하지 못해(LLM 호출 실패) 일반 이송 병원 목록에서 무작위로 골랐습니다."

# 출력 스키마의 병원 ID 값 목록
HospitalId = StrEnum("HospitalId", [(hospital_id, hospital_id) for hospital_id in GROUP_HOSPITAL_NAMES])


# 출력 모델의 docstring은 JSON 스키마의 description이 되어 프롬프트에 들어간다.
class StaticRecommendation(BaseModel):
    """추천 병원."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hospital_id: HospitalId
    reason: str


class StaticSelection(BaseModel):
    """6대 중증질환 판정과 추천 병원."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    disease_groups: tuple[DiseaseGroup, ...]
    recommendations: tuple[StaticRecommendation, ...]


def _hospital_tables() -> str:
    sections = []
    for group, hospitals in HOSPITALS_BY_GROUP.items():
        rows = "\n".join(f"- {h.hospital_id}, {h.hospital_name}, {h.transfer_count}건" for h in hospitals)
        sections.append(f"## {group}\n\n{rows}")
    return "\n\n".join(sections)


SYSTEM_PROMPT = Template(PROMPT_PATH.read_text(encoding="utf-8")).substitute(
    hospital_tables=_hospital_tables(),
    output_schema=json.dumps(StaticSelection.model_json_schema(), ensure_ascii=False),
)


def build_messages(req: RecommendRequest) -> list[ChatMessage]:
    data = build_input(req.patient)
    if req.patient.major_severe_type is not None:
        data["major_severe_type"] = req.patient.major_severe_type
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False, indent=2)},
    ]


def recommend(req: RecommendRequest, llm_client: LlmClient, rng: random.Random) -> RecommendResponse:
    count = req.recommend_count or settings.recommend_count
    rejected = {hospital.hospital_name for hospital in req.rejected_hospitals}

    result = llm_client.invoke(build_messages(req), StaticSelection, settings.llm_timeout_seconds)
    picked: list[tuple[str, str, str]] = []  # (병원 ID, 병원명, 추천 근거)
    fallback_reason = FALLBACK_REASON
    if isinstance(result, LlmFailure):
        logger.warning("정적 병원 선정 LLM 실패 reason=%s", result)
        fallback_reason = LLM_FAILURE_REASON
    else:
        logger.info("정적 병원 선정 LLM 출력 raw=%r", result.raw)
        for rec in result.parsed.recommendations:
            name = GROUP_HOSPITAL_NAMES[rec.hospital_id]
            if name not in rejected and all(rec.hospital_id != hospital_id for hospital_id, _, _ in picked):
                picked.append((rec.hospital_id, name, rec.reason))

    if not picked:
        candidates = [h for h in GENERAL_HOSPITALS if h.hospital_name not in rejected]
        sampled = rng.sample(candidates, min(count, len(candidates)))
        picked = [(h.hospital_id, h.hospital_name, fallback_reason) for h in sampled]

    return RecommendResponse(
        incident_id=req.incident_id,
        request_seq=req.request_seq,
        recommendations=[
            Recommendation(hospital_id=hospital_id, hospital_name=name, rank=rank, reason=reason)
            for rank, (hospital_id, name, reason) in enumerate(picked[:count], start=1)
        ],
    )
