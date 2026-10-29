"""119 이송지침 규칙 엔진(B) 테스트. PRD_v0.1.md F-05 '119 이송지침 규칙 엔진'의 분류별 규칙 표의 행마다 확인한다."""

import pytest
import yaml

from aimp.engines import guideline
from aimp.domain.types import HospitalCategory, Level, PatientCategory
from aimp.common.settings import CONFIG_DIR

REGIONAL_CENTER = HospitalCategory.REGIONAL_EMERGENCY_CENTER
LOCAL_CENTER = HospitalCategory.LOCAL_EMERGENCY_CENTER
LOCAL_INSTITUTION = HospitalCategory.LOCAL_EMERGENCY_INSTITUTION
TRAUMA_CENTER = HospitalCategory.REGIONAL_TRAUMA_CENTER


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (PatientCategory.SEVERE_TRAUMA, [{TRAUMA_CENTER}, {LOCAL_CENTER}]),
        (PatientCategory.MINOR_TRAUMA, [{LOCAL_INSTITUTION}]),
        (PatientCategory.SEVERE_NON_TRAUMA, [{REGIONAL_CENTER, LOCAL_CENTER}, {LOCAL_INSTITUTION}]),
        (PatientCategory.MINOR_NON_TRAUMA, [{LOCAL_INSTITUTION}]),
        (PatientCategory.CARDIAC_ARREST, [{REGIONAL_CENTER, LOCAL_CENTER, LOCAL_INSTITUTION}]),
        (PatientCategory.STROKE_SUSPECTED, [{REGIONAL_CENTER, LOCAL_CENTER}, {LOCAL_INSTITUTION}]),
        (PatientCategory.STROKE_SCREENING_POSITIVE, [{REGIONAL_CENTER, LOCAL_CENTER, LOCAL_INSTITUTION}, {LOCAL_INSTITUTION}]),
    ],
)
def test_levels_for_each_category(category, expected):
    """적용 규칙마다 L0, L1 순서로 병원 분류 조건을 반환하고, L1 조건이 없으면 L0 조건만 반환하는지 확인한다."""
    conditions = guideline.levels_for(category)

    assert [condition.level for condition in conditions] == [Level.L0, Level.L1][: len(expected)]
    assert [condition.categories for condition in conditions] == expected


@pytest.mark.parametrize(
    ("low", "high", "values", "severe"),
    [
        (90, None, [95, 89], True),
        (90, None, [120, 90], False),
        (None, 120, [100, 121], True),
        (None, 120, [80, 120], False),
        (10, 29, [18, 9], True),
        (10, 29, [18, 30], True),
        (10, 29, [10, 29], False),
        (None, None, [0, 999], False),
    ],
)
def test_vital_threshold_uses_worst_value(low, high, values, severe):
    """기록 중 가장 낮은 값이 low보다 작거나 가장 높은 값이 high보다 클 때만 중증인지 확인한다.

    임계치와 같은 값은 중증이 아니고, 임계치를 하나도 적지 않은 항목은 중증으로 판정하지 않는다.
    """
    assert guideline.VitalThreshold(low=low, high=high).is_severe(values) is severe


def test_config_version_is_loaded():
    """규칙 설정 파일의 버전을 읽는지 확인한다."""
    assert guideline.RULES.version == "0.2"


def _remove_version(config):
    del config["version"]


def _undefined_hospital_category(config):
    config["levels"]["비외상 중증"]["L0"].append("전문응급의료센터")


def _missing_category(config):
    del config["levels"]["경증외상"]


def _missing_l0(config):
    del config["levels"]["중증외상"]["L0"]


def _empty_level(config):
    config["levels"]["중증외상"]["L1"] = []


def _unknown_trauma_vital_sign(config):
    config["trauma_vital_signs"]["heart_rate"] = {"high": 120}


def _unknown_non_trauma_vital_sign(config):
    config["non_trauma_vital_signs"]["heart_rate"] = {"high": 120}


def _unknown_threshold_key(config):
    config["trauma_vital_signs"]["systolic_bp_mm_hg"] = {"worse": "low", "threshold": 90}


def _missing_non_trauma_vital_signs(config):
    del config["non_trauma_vital_signs"]


@pytest.mark.parametrize(
    "mutate",
    [
        _remove_version,
        _undefined_hospital_category,
        _missing_category,
        _missing_l0,
        _empty_level,
        _unknown_trauma_vital_sign,
        _unknown_non_trauma_vital_sign,
        _unknown_threshold_key,
        _missing_non_trauma_vital_signs,
    ],
)
def test_malformed_config_fails_to_load(tmp_path, mutate):
    """실제 규칙 설정 파일을 한 곳씩 틀리게 바꾸면 설정 파일을 읽지 못하는지 확인한다."""
    config = yaml.safe_load((CONFIG_DIR / "transfer_rules.yaml").read_text(encoding="utf-8"))
    mutate(config)
    path = tmp_path / "transfer_rules.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValueError):
        guideline.load(path)


def test_duplicate_key_fails_to_load(tmp_path):
    """같은 적용 규칙을 두 번 적으면 마지막 값을 쓰지 않고 설정 파일을 읽지 못하는지 확인한다."""
    text = (CONFIG_DIR / "transfer_rules.yaml").read_text(encoding="utf-8")
    assert text.count("levels:\n") == 1
    path = tmp_path / "transfer_rules.yaml"
    path.write_text(text.replace("levels:\n", "levels:\n  경증외상:\n    L0: [권역외상센터]\n"), encoding="utf-8")

    with pytest.raises(ValueError, match="경증외상"):
        guideline.load(path)
