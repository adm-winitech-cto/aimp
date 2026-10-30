"""처리 흐름. PRD_v0.1.md §3 '처리 순서'대로 처리 단계를 호출하고, 각 단계가 낸 경고를 모은다.

구현된 처리 단계를 하나씩 붙이는 중이다(#48). 아직 붙이지 않은 단계는 건너뛰고,
최종 선정 fallback(#19)을 붙이기 전까지는 후보 병원 중 직선거리가 가까운 병원 N개를 추천한다.
"""

from dataclasses import dataclass

from aimp.api.request import RecommendRequest
from aimp.classification import patient_assessment, severe_resource, severity
from aimp.common.settings import settings
from aimp.domain.hospital import Hospital
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Level, PatientCategory, WarningCode
from aimp.engines import guideline, travel
from aimp.ports.hospital_repository import HospitalRepository
from aimp.ports.llm import LlmClient


@dataclass(frozen=True)
class RecommendedHospital:
    """추천 병원 하나. 결과 객체의 추천 병원 목록에서 놓인 순서가 순위다."""

    hospital_id: str
    hospital_name: str
    reason: str


@dataclass(frozen=True)
class PipelineResult:
    """처리 흐름의 결과. api/가 응답 JSON으로 바꾼다."""

    recommendations: tuple[RecommendedHospital, ...]  # 1순위부터. 후보 병원이 0곳이면 비어 있다
    warnings: tuple[WarningCode, ...]
    severe_judgment: SevereJudgment  # A0: 4대 중증 구분, 적용 규칙, 특수 자원
    assessment: PatientAssessment | None  # A1: 환자 상태 판단 결과. LLM이 실패하면 None
    category: PatientCategory  # 적용 규칙. 4대 중증이면 A0이, 아니면 A2가 정한다
    special_situations: tuple[str, ...]  # 외상 환자의 특수상황 항목. 항목이 있으면 "직접의료지도 필요"
    level: Level | None  # 후보 병원을 고른 레벨. L1 조건으로도 후보 병원이 0곳이면 None

    @property
    def medical_direction_needed(self) -> bool:
        """L1 조건으로 후보 병원을 골랐으면 "의료지도 필요"."""
        return self.level == Level.L1


def run(req: RecommendRequest, llm_client: LlmClient, hospital_repository: HospitalRepository) -> PipelineResult:
    warnings: list[WarningCode] = []  # 각 단계가 경고를 이 목록에 추가
    if req.patient.vital_signs is None:  # 4대 중증 환자를 포함한 모든 환자
        warnings.append(WarningCode.NO_VITAL_SIGNS)
    severe_judgment = severe_resource.judge(req.patient)  # A0
    assessment = patient_assessment.assess(req.patient, llm_client, warnings)  # A1, 모든 환자. LLM이 실패하면 None
    # A2, 4대 중증이 아닐 때만. assessment가 None이면 비외상 기준
    category = severe_judgment.category or severity.judge(req.patient, assessment)
    special = severity.special_situations(req.patient, category, assessment)  # 외상 환자만

    levels = guideline.levels_for(category)  # B: [L0 조건, L1 조건]
    location = req.patient.location
    # C0: L0·L1 조건의 병원 분류를 합쳐 한 번만 조회한다. 조회가 실패하면 HospitalLookupError가 그대로 나간다.
    hospitals = hospital_repository.find_by_categories(
        location.longitude, location.latitude, frozenset().union(*(condition.categories for condition in levels))
    )
    level: Level | None = None
    candidates: list[Hospital] = []
    for condition in levels:  # C: 후보 병원이 0곳이면 다음 레벨. L1 조건으로도 0곳이면 추천하지 않는다
        candidates = [hospital for hospital in hospitals if hospital.categories & condition.categories]
        if candidates:
            level = condition.level
            break

    # C: 도착시간·거리 규칙 엔진. 직선거리가 가까운 후보 병원 M개(llm_candidate_count)만 남긴다
    candidates = travel.nearest(candidates)

    # E 자리: 최종 선정 fallback(#19)을 붙이기 전까지 직선거리가 가까운 병원 N개를 추천한다.
    picked = candidates[: req.recommend_count or settings.recommend_count]
    return PipelineResult(
        recommendations=tuple(
            RecommendedHospital(hospital_id=h.hospital_id, hospital_name=h.name, reason=f"직선거리 {h.distance_km:.1f}km")
            for h in picked
        ),
        warnings=tuple(warnings),
        severe_judgment=severe_judgment,
        assessment=assessment,
        category=category,
        special_situations=special,
        level=level,
    )
