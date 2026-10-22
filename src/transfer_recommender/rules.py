"""119 이송지침 규칙 엔진(B). 적용 규칙을 받아 레벨별 병원 등급 조건을 반환한다.

규칙 설정 파일(config/transfer_rules.yaml)에는 중증도 판정(A2)의 활력징후 임계치도 들어 있다.
설정 파일은 모듈을 import할 때 읽는다. 형식이 틀리면 import가 실패하므로 앱이 기동되지 않는다.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from transfer_recommender.api.request import VitalSign
from transfer_recommender.domain.types import HospitalCategory, Level, PatientCategory
from transfer_recommender.settings import CONFIG_DIR, load_yaml

# 활력징후 기록에서 임계치를 둘 수 있는 측정 항목(숫자 필드)
VITAL_SIGN_MEASUREMENTS = {name for name, field in VitalSign.model_fields.items() if field.annotation == float | None}


@dataclass(frozen=True)
class LevelCondition:
    """레벨 하나의 병원 등급 조건. 병원이 categories 중 하나 이상에 속하면 조건을 만족한다."""

    level: Level
    categories: frozenset[HospitalCategory]


class VitalThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    low: float | None = None  # 기록 중 가장 낮은 값이 이 값보다 작으면 중증
    high: float | None = None  # 기록 중 가장 높은 값이 이 값보다 크면 중증

    def is_severe(self, values: list[float]) -> bool:
        """기록 중 가장 나쁜 값이 임계치를 넘으면 True. 임계치가 하나도 없으면 False."""
        return (self.low is not None and min(values) < self.low) or (self.high is not None and max(values) > self.high)


class TransferRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    levels: dict[PatientCategory, dict[Level, Annotated[frozenset[HospitalCategory], Field(min_length=1)]]]
    trauma_vital_signs: dict[str, VitalThreshold]  # 외상 환자의 활력징후 임계치
    non_trauma_vital_signs: dict[str, VitalThreshold]  # 비외상 환자의 활력징후 임계치
    normal_consciousness_levels: Annotated[frozenset[str], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_complete(self) -> "TransferRules":
        missing = [category.value for category in PatientCategory if category not in self.levels]
        if missing:
            raise ValueError(f"levels에 적용 규칙이 없습니다: {missing}")
        without_l0 = [category.value for category, levels in self.levels.items() if Level.L0 not in levels]
        if without_l0:
            raise ValueError(f"L0 조건이 없습니다: {without_l0}")
        for key in ("trauma_vital_signs", "non_trauma_vital_signs"):
            unknown = sorted(getattr(self, key).keys() - VITAL_SIGN_MEASUREMENTS)
            if unknown:
                raise ValueError(f"{key}에 활력징후 측정 항목이 아닌 키가 있습니다: {unknown}")
        return self


def load(path: Path) -> TransferRules:
    """YAML 문법이 틀리면 yaml.YAMLError를, 내용 형식이 틀리면 ValueError(pydantic ValidationError 포함)를 낸다."""
    return TransferRules.model_validate(load_yaml(path))


RULES = load(CONFIG_DIR / "transfer_rules.yaml")


def levels_for(category: PatientCategory) -> list[LevelCondition]:
    """[L0 조건, L1 조건]. L1 조건이 없는 적용 규칙은 [L0 조건]."""
    levels = RULES.levels[category]
    return [LevelCondition(level, levels[level]) for level in Level if level in levels]
