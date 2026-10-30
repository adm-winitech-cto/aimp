"""설정값과 설정 파일 로더.

설정값은 config/settings.yaml에 있다. 각 값의 뜻과 출처(PRD_v0.1.md의 예시값, 임시값)는 그 파일의 주석에 적는다.
설정 파일은 모듈을 import할 때 읽는다. 형식이 틀리면 import가 실패하므로 앱이 기동되지 않는다.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

# 코드 수정 없이 바꾸는 설정 파일(설정값, 규칙 설정)의 위치. 저장소 루트의 config/
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


class _UniqueKeyLoader(yaml.SafeLoader):
    """같은 매핑 안에 같은 키가 두 번 이상 나오면 실패하는 YAML 로더. PyYAML 기본 로더는 오류 없이 마지막 값을 쓴다."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(key_node, deep=deep) for key_node, _ in node.value]
        duplicates = sorted({str(key) for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ValueError(f"{node.start_mark.line + 1}번째 줄의 매핑에 같은 키가 두 번 이상 있습니다: {duplicates}")
        return super().construct_mapping(node, deep=deep)


def load_yaml(path: Path) -> Any:
    """설정 파일을 읽는다. YAML 문법이 틀리면 yaml.YAMLError를, 같은 키가 두 번 이상 나오면 ValueError를 낸다."""
    with path.open(encoding="utf-8") as f:
        return yaml.load(f, Loader=_UniqueKeyLoader)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recommend_count: int
    llm_candidate_count: int
    detour_threshold_km: float
    bed_data_max_age_minutes: int
    require_icu_beds: bool
    assessment_timeout_seconds: float
    llm_timeout_seconds: float
    vllm_max_waiting_requests: int
    assessment_prompt_version: str
    prompt_version: str
    vllm_url: str
    vllm_model: str
    hospital_api_url: str
    hospital_api_timeout_seconds: float
    hospital_api_max_concurrency: int
    hospital_search_radius_km: float
    tmap_eta_url: str
    tmap_eta_timeout_seconds: float
    tmap_app_key: str


def load(path: Path) -> Settings:
    """YAML 문법이 틀리면 yaml.YAMLError를, 내용 형식이 틀리면 ValueError(pydantic ValidationError 포함)를 낸다."""
    return Settings.model_validate(load_yaml(path))


settings = load(CONFIG_DIR / "settings.yaml")
