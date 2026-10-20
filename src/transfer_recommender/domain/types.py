"""여러 처리 단계가 공유하는 열거형."""

from enum import StrEnum


class SevereType(StrEnum):
    """4대 중증 구분."""

    CARDIAC_ARREST = "심정지"
    SEVERE_TRAUMA = "중증외상"
    STROKE = "뇌졸중"
    MYOCARDIAL_INFARCTION = "심근경색"


class PatientCategory(StrEnum):
    """적용 규칙. design.md '119 이송지침 규칙 엔진'의 환자 분류."""

    SEVERE_TRAUMA = "중증외상"
    MINOR_TRAUMA = "경증외상"
    SEVERE_NON_TRAUMA = "비외상 중증"
    MINOR_NON_TRAUMA = "비외상 경증"
    CARDIAC_ARREST = "심폐정지"
    STROKE_SUSPECTED = "뇌졸중 의증"
    STROKE_SCREENING_POSITIVE = "뇌졸중 선별검사 양성"


class Level(StrEnum):
    """L0은 지침의 원칙 조건, L1은 의료지도를 받아야 적용할 수 있는 완화 조건."""

    L0 = "L0"
    L1 = "L1"


class Resource(StrEnum):
    """환자에게 필요한 특수 자원. design.md '판정 규칙' 표."""

    STROKE_TREATMENT = "뇌경색 재관류중재술 또는 뇌출혈수술"
    MI_REPERFUSION = "심근경색 재관류중재술"
    PEDIATRIC_EMERGENCY = "소아 응급 진료"
    DELIVERY = "분만"


class WarningCode(StrEnum):
    """시스템이 응답에 포함하는 경고."""

    PRE_KTAS_UNREGISTERED = "평가내용 미등록"
    NO_VITAL_SIGNS = "활력징후 없음"
    STALE_BED_DATA = "병상 정보 오래됨"
    REMARK_NOT_APPLIED = "비고 미반영"
