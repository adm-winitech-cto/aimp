"""추천 결과. 처리 흐름(pipeline.py)의 출력이고, api/가 응답 JSON으로 바꾼다."""

from dataclasses import dataclass

from aimp.domain.eta import Eta
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Level, PatientCategory, WarningCode
from aimp.ports.llm import LlmFailure


@dataclass(frozen=True)
class RecommendedHospital:
    """추천 병원 하나. 결과 객체의 추천 병원 목록에서 놓인 순서가 순위다."""

    hospital_id: str
    hospital_name: str
    reason: str
    eta: Eta  # Tmap ETA API로 구한 ETA. 실패하면 직선거리로 대신한다


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
    # 최종 선정 fallback으로 추천했으면 True. 후보 병원이 0곳이면 병원을 고르지 않으므로 False
    fallback: bool
    # 최종 선정 fallback 사유(최종 선정 LLM의 실패 사유). 최종 선정 LLM을 연결하기 전(#18)에는 LLM을 부르지 않으므로 None
    fallback_reason: LlmFailure | None

    @property
    def medical_direction_needed(self) -> bool:
        """L1 조건으로 후보 병원을 골랐으면 "의료지도 필요"."""
        return self.level == Level.L1
