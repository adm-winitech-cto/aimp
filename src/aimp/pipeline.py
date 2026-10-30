"""처리 흐름. PRD_v0.1.md §3 '처리 순서'대로 처리 단계를 호출하고, 각 단계가 낸 경고를 모은다.

구현된 처리 단계를 하나씩 붙이는 중이다(#48). 아직 붙이지 않은 단계는 건너뛰고,
추천 병원은 임시 선정 단계(selection/static_selection.py)가 정한다.
"""

import random
from dataclasses import dataclass

from aimp.api.request import RecommendRequest
from aimp.domain.types import WarningCode
from aimp.ports.llm import LlmClient
from aimp.selection import static_selection


@dataclass(frozen=True)
class RecommendedHospital:
    """추천 병원 하나. 결과 객체의 추천 병원 목록에서 놓인 순서가 순위다."""

    hospital_id: str
    hospital_name: str
    reason: str


@dataclass(frozen=True)
class PipelineResult:
    """처리 흐름의 결과. api/가 응답 JSON으로 바꾼다."""

    recommendations: tuple[RecommendedHospital, ...]  # 1순위부터
    warnings: tuple[WarningCode, ...]


def run(req: RecommendRequest, llm_client: LlmClient, rng: random.Random) -> PipelineResult:
    warnings: list[WarningCode] = []
    selected = static_selection.recommend(req, llm_client, rng)
    return PipelineResult(
        recommendations=tuple(
            RecommendedHospital(hospital_id=r.hospital_id, hospital_name=r.hospital_name, reason=r.reason)
            for r in selected.recommendations
        ),
        warnings=tuple(warnings),
    )
