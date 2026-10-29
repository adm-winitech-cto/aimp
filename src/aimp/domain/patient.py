"""환자 분류 결과. 중증·특수 자원 판단(A0)과 환자 상태 판단(A1)의 출력."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from aimp.domain.types import (
    Department,
    PatientCategory,
    Resource,
    SevereDiseaseCode,
    SevereType,
    TraumaCriterion,
)


@dataclass(frozen=True)
class SevereJudgment:
    """중증·특수 자원 판단(A0) 결과. 4대 중증이면 category에 적용 규칙이 들어가고, 아니면 None이다."""

    severe_type: SevereType | None
    category: PatientCategory | None
    required_resources: frozenset[Resource]


# 환자 상태 판단(A1) LLM의 출력 스키마이자, 중증도 판정(A2)과 후보 필터(C)가 받는 결과 타입이다.
# - 필드에 기본값을 두지 않는다. 그래야 JSON 스키마의 required에 모든 키가 들어가 LLM이 모든 키를 출력한다.
# - extra="forbid"는 JSON 스키마에 additionalProperties: false를 넣는다.
# - docstring은 JSON 스키마의 description이 되어 프롬프트에 들어간다.
class PatientAssessment(BaseModel):
    """환자 상태 판단 결과."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_trauma: bool
    required_depts: tuple[Department, ...]
    supportive_depts: tuple[Department, ...]
    severe_disease_code: SevereDiseaseCode | None
    trauma_criteria: tuple[TraumaCriterion, ...]
