"""추천 사유 템플릿. 최종 선정(E)과 최종 선정 fallback이 추천 사유 문자열(응답의 reason)을 만들 때 함께 쓴다.

- 최종 선정 LLM은 병원마다 템플릿 id만 고르고, 문장에 들어갈 값(진료과 이름, 병상 수, 직선거리 등)은 이 모듈이 병원
  데이터와 환자 판단 결과에서 채운다. LLM이 사유 문장과 숫자를 직접 쓰지 않으므로 출력 토큰이 줄고 숫자가 틀리지 않는다.
- 최종 선정 fallback은 정해진 템플릿 목록(PRD_v0.1.md F-09)으로 같은 문장을 만든다.
- 채울 값이 없는 템플릿은 사유를 만들지 않는다(None). 남은 사유가 하나도 없을 때의 처리는 사용하는 쪽이 정한다.
- ETA는 최종 선정이 끝난 뒤 추천 병원에만 구하므로 템플릿이 아니다. join_reasons가 마지막에 붙인다.
- 환자에게 필요할 것으로 판단한 진료과와 특수 자원(patient_needs)도 템플릿이 아니다. 추천 병원 모두에 같으므로
  LLM이 병원마다 고르지 않고, 처리 흐름이 모든 추천 병원의 사유 맨 앞에 붙인다.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from aimp.domain.eta import Eta, EtaMethod
from aimp.domain.hospital import AcceptanceStatus, CongestionStatus
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import SEVERE_DISEASE_NAMES, HospitalCategory, Resource
from aimp.engines.capability import RESOURCE_CONDITIONS, CandidateHospital
from aimp.engines.guideline import LevelCondition

STALE_SUFFIX = "(병상 정보 오래됨)"


class ReasonTemplate(StrEnum):
    """추천 사유 템플릿 id. 문장 틀은 render의 주석에 적는다."""

    GRADE = "grade"
    REQUIRED_DEPT = "required_dept"
    SEVERE_DISEASE = "severe_disease"
    SPECIAL_RESOURCE = "special_resource"
    ER_BEDS = "er_beds"
    ICU_BEDS = "icu_beds"
    DELIVERY = "delivery"
    CONGESTION = "congestion"
    DISTANCE = "distance"
    REMARK = "remark"


@dataclass(frozen=True)
class PatientContext:
    """템플릿 값을 채울 때 쓰는 환자 쪽 데이터."""

    condition: LevelCondition  # 후보 병원을 고른 레벨의 병원 등급 조건
    severe_judgment: SevereJudgment
    assessment: PatientAssessment | None  # 환자 상태 판단이 실패했으면 None


def render(
    template: ReasonTemplate, candidate: CandidateHospital, patient: PatientContext, quote: str | None = None
) -> str | None:
    """템플릿 하나를 채운 사유 문장. 채울 값이 없으면 None이다. quote는 REMARK 템플릿의 비고 원문 인용이다."""
    hospital = candidate.hospital
    stale = STALE_SUFFIX if candidate.stale_beds else ""
    assessment = patient.assessment
    match template:
        case ReasonTemplate.GRADE:  # "{병원 분류} 조건 충족". 병원 분류 중 레벨 조건에 맞은 것
            matched = [c for c in HospitalCategory if c in hospital.categories and c in patient.condition.categories]
            return f"{'·'.join(matched)} 조건 충족" if matched else None
        case ReasonTemplate.REQUIRED_DEPT:  # "{진료과} 진료 가능". 필수 진료과 중 병원이 가진 것
            depts = [d for d in assessment.required_depts if d in hospital.departments] if assessment else []
            return f"{'·'.join(depts)} 진료 가능" if depts else None
        case ReasonTemplate.SEVERE_DISEASE:  # "{중증질환} 수용 가능". 수용가능 값이 Y일 때만
            code = assessment.severe_disease_code if assessment else None
            acceptance = hospital.disease_acceptance.get(code) if code else None
            if acceptance is None or acceptance.status != AcceptanceStatus.AVAILABLE:
                return None
            return f"{SEVERE_DISEASE_NAMES[code]} 수용 가능"
        case ReasonTemplate.SPECIAL_RESOURCE:  # "{특수 자원} 가능". 분만은 DELIVERY 템플릿이 맡는다
            resources = [
                r for r, satisfied in RESOURCE_CONDITIONS.items()
                if r in patient.severe_judgment.required_resources and satisfied(hospital)
            ]
            return f"{'·'.join(resources)} 가능" if resources else None
        case ReasonTemplate.ER_BEDS:  # "응급실 가용병상 {n}"
            available = hospital.er_beds.available
            return f"응급실 가용병상 {available}{stale}" if available is not None else None
        case ReasonTemplate.ICU_BEDS:  # "중환자실 가용병상 {n}". 값이 있는 병상 종류의 합
            counts = [beds.available for beds in hospital.icu_beds.values() if beds.available is not None]
            return f"중환자실 가용병상 {sum(counts)}{stale}" if counts else None
        case ReasonTemplate.DELIVERY:  # "분만 가능". 진료 역량 규칙 엔진의 "분만 가능" 태그
            return "분만 가능" if candidate.can_deliver else None
        case ReasonTemplate.CONGESTION:  # "응급실 {혼잡 상태}"
            status = hospital.congestion_status
            return f"응급실 {status}" if status != CongestionStatus.NO_DATA else None
        case ReasonTemplate.DISTANCE:  # "직선거리 {km}km"
            return f"직선거리 {hospital.distance_km:.1f}km"
        case ReasonTemplate.REMARK:  # '비고: "{인용}"'. 인용이 비고 원문에 있는지는 최종 선정의 출력 검증이 확인한다
            return f'비고: "{quote}"' if quote else None


def patient_needs(patient: PatientContext) -> tuple[str, ...]:
    """환자에게 필요할 것으로 판단한 것. "{필수 진료과} 진료 필요 예상", "{특수 자원} 필요 예상" 순서이고, 값이 없으면 뺀다.

    필수 진료과는 환자 상태 판단(A1), 특수 자원은 중증·특수 자원 판단(A0)의 결과다. 특수 자원에는 분만도 넣는다.
    """
    depts = patient.assessment.required_depts if patient.assessment else ()
    resources = [r for r in Resource if r in patient.severe_judgment.required_resources]
    needs = []
    if depts:
        needs.append(f"{'·'.join(depts)} 진료 필요 예상")
    if resources:
        needs.append(f"{'·'.join(resources)} 필요 예상")
    return tuple(needs)


def join_reasons(reasons: Iterable[str | None], eta: Eta) -> str:
    """채운 사유를 ', '로 이어 붙인다. None은 뺀다. Tmap ETA API로 ETA를 구했으면 마지막에 도착 예정 시간을 붙인다."""
    parts = [reason for reason in reasons if reason is not None]
    if eta.method == EtaMethod.TMAP and eta.travel_seconds is not None:
        parts.append(f"도착 예정 {max(1, round(eta.travel_seconds / 60))}분")
    return ", ".join(parts)
