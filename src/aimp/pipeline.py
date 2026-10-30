"""처리 흐름. PRD_v0.1.md §3 '처리 순서'대로 처리 단계를 호출하고, 각 단계가 낸 경고를 모은다.

구현된 처리 단계를 하나씩 붙이는 중이다(#48). 아직 붙이지 않은 단계는 건너뛰고,
추천 병원은 임시 선정 단계(selection/static_selection.py)가 정한다.
"""

import random
from dataclasses import dataclass

from aimp.api.request import RecommendRequest
from aimp.classification import patient_assessment, severe_resource, severity
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import PatientCategory, WarningCode
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
    severe_judgment: SevereJudgment  # A0: 4대 중증 구분, 적용 규칙, 특수 자원
    assessment: PatientAssessment | None  # A1: 환자 상태 판단 결과. LLM이 실패하면 None
    category: PatientCategory  # 적용 규칙. 4대 중증이면 A0이, 아니면 A2가 정한다
    special_situations: tuple[str, ...]  # 외상 환자의 특수상황 항목. 항목이 있으면 "직접의료지도 필요"


def run(req: RecommendRequest, llm_client: LlmClient, rng: random.Random) -> PipelineResult:
    warnings: list[WarningCode] = []  # 각 단계가 경고를 이 목록에 추가
    if req.patient.vital_signs is None:  # 4대 중증 환자를 포함한 모든 환자
        warnings.append(WarningCode.NO_VITAL_SIGNS)
    severe_judgment = severe_resource.judge(req.patient)  # A0
    assessment = patient_assessment.assess(req.patient, llm_client, warnings)  # A1, 모든 환자. LLM이 실패하면 None
    # A2, 4대 중증이 아닐 때만. assessment가 None이면 비외상 기준
    category = severe_judgment.category or severity.judge(req.patient, assessment)
    special = severity.special_situations(req.patient, category, assessment)  # 외상 환자만
    selected = static_selection.recommend(req, llm_client, rng)
    return PipelineResult(
        recommendations=tuple(
            RecommendedHospital(hospital_id=r.hospital_id, hospital_name=r.hospital_name, reason=r.reason)
            for r in selected.recommendations
        ),
        warnings=tuple(warnings),
        severe_judgment=severe_judgment,
        assessment=assessment,
        category=category,
        special_situations=special,
    )
