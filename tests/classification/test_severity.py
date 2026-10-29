"""중증도 판정(A2)과 특수상황 판정 테스트."""

import pytest

from aimp.api.request import Patient
from aimp.classification import severity
from aimp.domain.patient import PatientAssessment
from aimp.domain.types import Department, PatientCategory, TraumaCriterion

TRAUMA = PatientAssessment(
    is_trauma=True,
    required_depts=(Department.ORTHOPEDIC_SURGERY,),
    supportive_depts=(),
    severe_disease_code=None,
    trauma_criteria=(),
)
NON_TRAUMA = PatientAssessment(
    is_trauma=False, required_depts=(), supportive_depts=(), severe_disease_code=None, trauma_criteria=()
)


def _trauma_with(*criteria: TraumaCriterion) -> PatientAssessment:
    return TRAUMA.model_copy(update={"trauma_criteria": criteria})


def _judge(body: dict, assessment: PatientAssessment | None) -> PatientCategory:
    return severity.judge(Patient.model_validate(body), assessment)


def _special(body: dict, category: PatientCategory, assessment: PatientAssessment | None) -> tuple[str, ...]:
    return severity.special_situations(Patient.model_validate(body), category, assessment)


def _set_vitals(body: dict, vitals: dict) -> None:
    """예시 요청의 활력징후에서 지정한 항목만 바꾼다."""
    body["vitalSigns"] = {**body["vitalSigns"], **vitals}


def test_open_fracture_example(example_patient):
    """발등 개방성 골절 예시(65세, Pre-KTAS 2단계, 외상, 활력징후 안정, 중증외상 기준 항목 없음)는
    경증외상이고, 특수상황 '위험한 나이'에 해당하는지 확인한다."""
    category = _judge(example_patient, TRAUMA)

    assert category == PatientCategory.MINOR_TRAUMA
    assert _special(example_patient, category, TRAUMA) == (severity.RISKY_AGE,)


@pytest.mark.parametrize(
    "vitals",
    [{"systolicBpMmHg": 85}, {"respiratoryRatePerMin": 9}, {"respiratoryRatePerMin": 30}],
    ids=["low-systolic-bp", "low-respiratory-rate", "high-respiratory-rate"],
)
@pytest.mark.parametrize("level", [2, 4])
def test_trauma_with_severe_vital_signs_is_severe_trauma(example_patient, vitals, level):
    """외상 환자의 활력징후가 지침의 생리학적 기준에 해당하면 Pre-KTAS 단계와 관계없이 중증외상이 되는지 확인한다."""
    example_patient["preKtas"]["level"] = level
    _set_vitals(example_patient, vitals)

    assert _judge(example_patient, TRAUMA) == PatientCategory.SEVERE_TRAUMA


@pytest.mark.parametrize("respiratory_rate", [10, 29])
def test_trauma_vital_signs_equal_to_threshold_are_not_severe(example_patient, respiratory_rate):
    """외상 환자의 수축기혈압 90, 호흡수 10과 29는 생리학적 기준(90 미만, 10 미만 또는 29 초과)에 해당하지 않는지 확인한다."""
    example_patient["preKtas"]["level"] = 4
    _set_vitals(example_patient, {"systolicBpMmHg": 90, "respiratoryRatePerMin": respiratory_rate})

    assert _judge(example_patient, TRAUMA) == PatientCategory.MINOR_TRAUMA


def test_trauma_ignores_spo2(example_patient):
    """산소포화도는 지침의 생리학적 기준이 아니므로, 외상 환자는 산소포화도가 90% 미만이어도 경증외상인지 확인한다."""
    example_patient["preKtas"]["level"] = 4
    _set_vitals(example_patient, {"spo2Percent": 85})

    assert _judge(example_patient, TRAUMA) == PatientCategory.MINOR_TRAUMA


def test_trauma_with_abnormal_consciousness_is_severe_trauma(example_patient):
    """외상 환자의 의식상태가 정상 목록에 없으면 중증외상이 되는지 확인한다."""
    example_patient["preKtas"]["level"] = 4
    example_patient["consciousnessLevel"] = "통증반응"

    assert _judge(example_patient, TRAUMA) == PatientCategory.SEVERE_TRAUMA


@pytest.mark.parametrize("criterion", [TraumaCriterion.PELVIC_FRACTURE, TraumaCriterion.FALL])
def test_injury_finding_or_mechanism_makes_severe_trauma(example_patient, criterion):
    """활력징후가 정상이어도 신체검사 소견이나 손상기전 항목이 있으면 중증외상이 되는지 확인한다."""
    example_patient["preKtas"]["level"] = 4

    assert _judge(example_patient, _trauma_with(criterion)) == PatientCategory.SEVERE_TRAUMA


def test_special_situation_alone_is_minor_trauma(example_patient):
    """특수상황 항목은 중증외상 판정에 쓰지 않으므로, 특수상황 항목만 있으면 경증외상인지 확인한다."""
    example_patient["preKtas"]["level"] = 4
    assessment = _trauma_with(TraumaCriterion.ANTICOAGULATION_OR_BLEEDING_DISORDER)

    assert _judge(example_patient, assessment) == PatientCategory.MINOR_TRAUMA


@pytest.mark.parametrize(
    ("level", "category"),
    [(2, PatientCategory.SEVERE_TRAUMA), (3, PatientCategory.MINOR_TRAUMA)],
)
def test_trauma_without_vital_signs_uses_pre_ktas_level(example_patient, level, category):
    """외상 환자의 활력징후가 null이면 Pre-KTAS 단계로 판정하는지 확인한다."""
    example_patient["preKtas"]["level"] = level
    example_patient["vitalSigns"] = None

    assert _judge(example_patient, TRAUMA) == category


def test_trauma_without_thresholded_measurements_uses_pre_ktas_level(example_patient):
    """활력징후는 있지만 수축기혈압과 호흡수가 모두 null이면, 외상 환자를 Pre-KTAS 단계로 판정하는지 확인한다.

    산소포화도는 외상 환자의 임계치 항목이 아니므로 측정값이 있어도 Pre-KTAS 단계를 쓴다.
    """
    _set_vitals(example_patient, {"systolicBpMmHg": None, "respiratoryRatePerMin": None, "spo2Percent": 97})

    assert _judge(example_patient, TRAUMA) == PatientCategory.SEVERE_TRAUMA


@pytest.mark.parametrize(
    ("level", "vitals", "category"),
    [
        (2, {}, PatientCategory.SEVERE_NON_TRAUMA),
        (4, {"systolicBpMmHg": 85}, PatientCategory.SEVERE_NON_TRAUMA),
        (4, {"spo2Percent": 88}, PatientCategory.SEVERE_NON_TRAUMA),
        (4, {"respiratoryRatePerMin": 35}, PatientCategory.MINOR_NON_TRAUMA),
        (4, {}, PatientCategory.MINOR_NON_TRAUMA),
    ],
    ids=["pre-ktas-severe", "low-systolic-bp", "low-spo2", "respiratory-rate-not-used", "minor"],
)
def test_non_trauma_takes_more_severe_judgment(example_patient, level, vitals, category):
    """비외상 환자는 Pre-KTAS 단계와 비외상 임계치(수축기혈압, 산소포화도) 중 하나라도 중증이면 비외상 중증이 되는지 확인한다."""
    example_patient["preKtas"]["level"] = level
    _set_vitals(example_patient, vitals)

    assert _judge(example_patient, NON_TRAUMA) == category


def test_null_measurements_are_skipped(example_patient):
    """null인 측정값은 건너뛰고 나머지 값으로 판정하는지 확인한다."""
    example_patient["preKtas"]["level"] = 4
    _set_vitals(example_patient, {"systolicBpMmHg": None, "spo2Percent": 97})

    assert _judge(example_patient, NON_TRAUMA) == PatientCategory.MINOR_NON_TRAUMA


def test_value_equal_to_threshold_is_not_severe(example_patient):
    """측정값이 임계치와 같으면 중증으로 판정하지 않는지 확인한다(임계치 90 미만이 중증)."""
    example_patient["preKtas"]["level"] = 4
    _set_vitals(example_patient, {"systolicBpMmHg": 90, "spo2Percent": 90})

    assert _judge(example_patient, NON_TRAUMA) == PatientCategory.MINOR_NON_TRAUMA


@pytest.mark.parametrize(
    ("level", "vitals", "category"),
    [
        (2, {}, PatientCategory.SEVERE_TRAUMA),
        (4, {"respiratoryRatePerMin": 30}, PatientCategory.SEVERE_TRAUMA),
        (4, {}, PatientCategory.MINOR_TRAUMA),
    ],
    ids=["pre-ktas-severe", "trauma-threshold", "minor"],
)
def test_missing_assessment_is_treated_as_trauma(example_patient, level, vitals, category):
    """환자 상태 판단 결과가 없으면 외상으로 보고, Pre-KTAS 1~2단계이거나 외상 임계치를 넘으면 중증외상인지 확인한다."""
    example_patient["preKtas"]["level"] = level
    _set_vitals(example_patient, vitals)

    assert _judge(example_patient, None) == category


@pytest.mark.parametrize(
    ("age", "risky"),
    [(10, True), (10.5, False), (54.9, False), (55, True)],
)
@pytest.mark.parametrize("category", sorted(severity.TRAUMA_CATEGORIES))
def test_risky_age(example_patient, age, risky, category):
    """적용 규칙이 중증외상(4대 중증 구분이 중증외상인 환자 포함)이나 경증외상이면, 55세 이상이거나 10세 이하일 때
    특수상황 '위험한 나이'에 해당하는지 확인한다."""
    example_patient["info"]["age"] = age

    assert _special(example_patient, category, TRAUMA) == ((severity.RISKY_AGE,) if risky else ())


def test_special_situation_criteria_are_added(example_patient):
    """환자 상태 판단 결과의 중증외상 기준 항목 중 특수상황 항목만 특수상황 판정 결과에 들어가는지 확인한다."""
    example_patient["info"]["age"] = 40
    assessment = _trauma_with(
        TraumaCriterion.PELVIC_FRACTURE,
        TraumaCriterion.ANTICOAGULATION_OR_BLEEDING_DISORDER,
        TraumaCriterion.PREGNANCY_OVER_20_WEEKS,
    )

    assert _special(example_patient, PatientCategory.SEVERE_TRAUMA, assessment) == (
        TraumaCriterion.ANTICOAGULATION_OR_BLEEDING_DISORDER,
        TraumaCriterion.PREGNANCY_OVER_20_WEEKS,
    )


@pytest.mark.parametrize("category", [PatientCategory.MINOR_NON_TRAUMA, PatientCategory.CARDIAC_ARREST])
def test_non_trauma_category_has_no_special_situations(example_patient, category):
    """적용 규칙이 외상이 아니면 나이나 특수상황 항목과 관계없이 특수상황 판정 결과가 비어 있는지 확인한다."""
    assessment = _trauma_with(TraumaCriterion.ANTICOAGULATION_OR_BLEEDING_DISORDER)

    assert _special(example_patient, category, assessment) == ()


def test_missing_assessment_judges_risky_age_only(example_patient):
    """환자 상태 판단 결과가 없으면 위험한 나이만 판정하는지 확인한다."""
    assert _special(example_patient, PatientCategory.MINOR_TRAUMA, None) == (severity.RISKY_AGE,)
