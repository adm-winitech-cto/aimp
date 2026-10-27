"""중증·특수 자원 판단(A0). design.md '판정 규칙' 표대로 입력 필드 값만 보고 판단한다."""

from transfer_recommender.api.request import Patient
from transfer_recommender.domain.patient import SevereJudgment
from transfer_recommender.domain.types import PatientCategory, Resource, SevereType

PEDIATRIC_AGE_LIMIT = 15  # 이 나이 미만이면 소아 응급 진료 자원이 필요하다.

# 4대 중증 구분 → (적용 규칙, 특수 자원)
_SEVERE_TYPE_RULES: dict[SevereType, tuple[PatientCategory, frozenset[Resource]]] = {
    # 심정지 환자에게 특수 자원이 없다는 판정은 design.md에서 잠정이다.
    SevereType.CARDIAC_ARREST: (PatientCategory.CARDIAC_ARREST, frozenset()),
    SevereType.SEVERE_TRAUMA: (PatientCategory.SEVERE_TRAUMA, frozenset()),
    # 뇌졸중 선별검사 결과를 받을 경로가 없으므로 '뇌졸중 의증' 규칙을 적용한다.
    SevereType.STROKE: (PatientCategory.STROKE_SUSPECTED, frozenset({Resource.STROKE_TREATMENT})),
    SevereType.MYOCARDIAL_INFARCTION: (PatientCategory.SEVERE_NON_TRAUMA, frozenset({Resource.MI_REPERFUSION})),
}


def judge(patient: Patient) -> SevereJudgment:
    category: PatientCategory | None = None
    resources: set[Resource] = set()
    if patient.major_severe_type is not None:
        category, severe_type_resources = _SEVERE_TYPE_RULES[patient.major_severe_type]
        resources |= severe_type_resources
    if patient.info.age < PEDIATRIC_AGE_LIMIT:
        resources.add(Resource.PEDIATRIC_EMERGENCY)
    # 신생아 정보(newbornInfo)는 우선 고려하지 않으므로 보지 않는다.
    if patient.special_info.pregnancy_info is not None:
        resources.add(Resource.DELIVERY)
    return SevereJudgment(patient.major_severe_type, category, frozenset(resources))
