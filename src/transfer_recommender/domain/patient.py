"""환자 분류 결과. 중증·특수 자원 판단(A0), Pre-KTAS 조회(A1), 중증도 판정(A2)의 출력."""

from dataclasses import dataclass

from transfer_recommender.domain.types import PatientCategory, Resource, SevereType


@dataclass(frozen=True)
class SevereJudgment:
    """중증·특수 자원 판단(A0) 결과. 4대 중증이면 적용 규칙은 severe_type에서 정해진다."""

    severe_type: SevereType | None
    required_resources: frozenset[Resource]


@dataclass(frozen=True)
class PreKtasLookup:
    """Pre-KTAS 조회(A1) 결과. Pre-KTAS 조회 테이블의 한 행."""

    is_trauma: bool
    required_depts: tuple[str, ...]
    supportive_depts: tuple[str, ...]
    severe_disease_code: str | None


@dataclass(frozen=True)
class Classification:
    """규칙 엔진(B)에 넘기는 환자 분류."""

    category: PatientCategory
    provisional: bool  # 잠정 중증외상 규칙으로 판정했으면 True
