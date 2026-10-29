"""중증도 판정(A2)과 외상 환자의 특수상황 판정.

중증도 판정: 4대 중증이 아닌 환자의 적용 규칙을 Pre-KTAS 단계, 활력징후, 의식상태, 환자 상태 판단 결과로 정한다.
활력징후 임계치와 정상 의식상태 목록은 config/transfer_rules.yaml에 있다.
- 생리학적 중증: 임계치를 둔 활력징후 항목의 값이 임계치를 넘거나, 의식상태가 정상 목록에 없으면 중증이다.
  외상 환자와 비외상 환자는 임계치가 다르다.
- 비외상 환자: Pre-KTAS 1~2단계이거나 생리학적 중증이면 비외상 중증, 아니면 비외상 경증이다.
- 외상 환자: "다발성/중증손상" 지침(docs/90_domain/severe-trauma-criteria.md)의 기준 중 하나라도 해당하면 중증외상, 아니면 경증외상이다.
    - 생리학적 기준: 외상 임계치로 판정한 생리학적 중증
    - 신체검사 소견·손상기전 기준: 환자 상태 판단 결과의 중증외상 기준 항목
    - 임계치를 둔 활력징후 항목의 측정값이 하나도 없으면 Pre-KTAS 1~2단계도 중증외상이다.
- 환자 상태 판단 결과가 없는 환자: 외상 여부와 중증외상 기준 항목을 알 수 없으므로 외상으로 본다.
  Pre-KTAS 1~2단계이거나 생리학적 중증이면 중증외상, 아니면 경증외상이다.

특수상황 판정: 적용 규칙이 중증외상이나 경증외상인 환자가 지침의 '의학적 질병상태 및 특수상황'에 해당하는 항목을 반환한다.
4대 중증 구분이 중증외상인 환자도 판정 대상이다. pipeline.py는 항목이 있으면 응답에 "직접의료지도 필요" 표시를 넣는다.

"활력징후 없음" 경고는 4대 중증 환자도 받아야 하므로 이 모듈이 아니라 pipeline.py가 추가한다.
"""

from transfer_recommender.api.request import Patient
from transfer_recommender.domain.patient import PatientAssessment
from transfer_recommender.domain.types import INJURY_FINDINGS, INJURY_MECHANISMS, SPECIAL_SITUATIONS, PatientCategory
from transfer_recommender.rules import RULES, VitalThreshold

SEVERE_PRE_KTAS_LEVEL = 2  # Pre-KTAS 단계가 이 값 이하면 중증이다.

# 특수상황 중 이 모듈이 나이로 판정하는 항목. 환자 상태 판단 LLM이 고르는 항목(TraumaCriterion)에는 없다.
RISKY_AGE = "위험한 나이: 성인 55세 이상, 소아 10세 이하"
RISKY_ADULT_AGE = 55  # 이 나이 이상이면 위험한 나이
RISKY_CHILD_AGE = 10  # 이 나이 이하이면 위험한 나이

TRAUMA_CATEGORIES = frozenset({PatientCategory.SEVERE_TRAUMA, PatientCategory.MINOR_TRAUMA})


def _physiological(patient: Patient, thresholds: dict[str, VitalThreshold]) -> tuple[bool, bool]:
    """(생리학적 중증 여부, 임계치를 둔 활력징후 항목의 측정값이 하나라도 있는지)."""
    measured = False
    vital_signs_severe = False
    for name, threshold in thresholds.items():
        value = getattr(patient.vital_signs, name) if patient.vital_signs is not None else None
        if value is not None:
            measured = True
            vital_signs_severe = vital_signs_severe or threshold.is_severe([value])
    return vital_signs_severe or patient.consciousness_level not in RULES.normal_consciousness_levels, measured


def judge(patient: Patient, assessment: PatientAssessment | None) -> PatientCategory:
    pre_ktas_severe = patient.pre_ktas.level <= SEVERE_PRE_KTAS_LEVEL

    if assessment is not None and not assessment.is_trauma:
        physiological_severe, _ = _physiological(patient, RULES.non_trauma_vital_signs)
        severe = pre_ktas_severe or physiological_severe
        return PatientCategory.SEVERE_NON_TRAUMA if severe else PatientCategory.MINOR_NON_TRAUMA

    physiological_severe, measured = _physiological(patient, RULES.trauma_vital_signs)
    if assessment is None:
        # 환자 상태 판단 결과가 없으면 외상으로 본다.
        severe = pre_ktas_severe or physiological_severe
    else:
        injury_severe = any(
            criterion in INJURY_FINDINGS or criterion in INJURY_MECHANISMS for criterion in assessment.trauma_criteria
        )
        severe = physiological_severe or injury_severe or (not measured and pre_ktas_severe)
    return PatientCategory.SEVERE_TRAUMA if severe else PatientCategory.MINOR_TRAUMA


def special_situations(
    patient: Patient, category: PatientCategory, assessment: PatientAssessment | None
) -> tuple[str, ...]:
    """특수상황 항목. 적용 규칙이 중증외상이나 경증외상이 아니면 빈 튜플이다.

    환자 상태 판단 결과가 없으면 위험한 나이만 판정한다.
    """
    if category not in TRAUMA_CATEGORIES:
        return ()
    age = patient.info.age
    items: list[str] = [RISKY_AGE] if age >= RISKY_ADULT_AGE or age <= RISKY_CHILD_AGE else []
    if assessment is not None:
        items += [criterion for criterion in assessment.trauma_criteria if criterion in SPECIAL_SITUATIONS]
    return tuple(items)
