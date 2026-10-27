"""병원 추천 요청 스키마. interface.md '병원 추천 요청'의 필드 표를 그대로 옮겼다.

검증 규칙:
- 타입에 null이 있거나 '생략 시 처리'가 null인 필드만 null을 받는다.
  그 밖의 필드(예: 생략 시 []인 `symptoms`, 생략 시 1인 `preKtas.assessmentRound`)에 null이 오면 검증에 실패한다.
- 숫자 필드는 JSON 숫자만 받는다. 불리언, 문자열(예: "65"), NaN, Infinity가 오면 검증에 실패한다.
- 명세에 없는 키가 오면 검증에 실패한다. 키 이름에 오타가 나서 값이 기본값으로 바뀌는 것을 막는다.

값 목록과 객체 구조가 미정인 필드는 문자열이나 임의 객체로 받는다(interface.md '미정 항목').
`majorSevereType`은 예외로 4대 중증 4종만 받는다. 시스템이 모르는 값을 무시하면 4대 중증 환자를 일반 환자로 분류하기 때문이다.
"""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, Strict
from pydantic.alias_generators import to_camel

from transfer_recommender.domain.types import SevereType

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None or parsed.strftime(TIMESTAMP_FORMAT) != value:
        raise ValueError("yyyy-MM-dd HH:mm:ss 형식의 문자열이어야 합니다")
    return parsed


Timestamp = Annotated[datetime, BeforeValidator(_parse_timestamp)]


class _RequestModel(BaseModel):
    # JSON 필드명은 camelCase, 파이썬 속성명은 snake_case
    model_config = ConfigDict(alias_generator=to_camel, strict=True, extra="forbid", allow_inf_nan=False)


class PatientInfo(_RequestModel):
    age: float = Field(ge=0)  # interface.md 타입이 number라 생후 6개월(0.5세) 같은 소수도 받는다.
    sex: str | None = None
    patient_type: str | None = None


class PreKtas(_RequestModel):
    assessment_round: int = Field(default=1, ge=1)
    level: int = Field(ge=1, le=5)
    assessment_detail: str


class VitalSign(_RequestModel):
    measured_at: Timestamp | None = None
    recorded_at: Timestamp
    systolic_bp_mm_hg: float | None = None
    diastolic_bp_mm_hg: float | None = None
    pulse_per_min: float | None = None
    respiratory_rate_per_min: float | None = None
    body_temp_celsius: float | None = None
    spo2_percent: float | None = None
    blood_glucose_mg_dl: float | None = None


class MedicalHistory(_RequestModel):
    disease_name: str
    detail: str | None = None


class SpecialPatientInfo(_RequestModel):
    # 키는 반드시 있어야 하고, 값이 null이면 '해당 없음'이다(interface.md '필수 여부 규칙'의 예외).
    pregnancy_info: dict[str, Any] | None
    newborn_info: dict[str, Any] | None


class PatientLocation(_RequestModel):
    # WGS84, 도 단위 십진수
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class Patient(_RequestModel):
    info: PatientInfo
    chief_complaint: str | None = None
    symptoms: list[str] = []
    consciousness_level: str
    # strict 모드는 열거형 인스턴스만 받으므로, 이 필드만 strict를 꺼서 문자열 값을 열거형으로 바꾼다.
    major_severe_type: Annotated[SevereType, Strict(False)] | None = None
    pre_ktas: PreKtas
    vital_signs: VitalSign | None = None
    medical_history: list[MedicalHistory] = []
    medications: list[Any] = []
    special_info: SpecialPatientInfo
    remark: str | None = None
    location: PatientLocation


class RejectedHospital(_RequestModel):
    hospital_name: str
    reason: str | None = None
    rejected_at: Timestamp


class RecommendRequest(_RequestModel):
    incident_id: str
    request_seq: int = Field(ge=1)
    requested_at: Timestamp
    recommend_count: int | None = Field(default=None, ge=1)
    patient: Patient
    rejected_hospitals: list[RejectedHospital] = []
