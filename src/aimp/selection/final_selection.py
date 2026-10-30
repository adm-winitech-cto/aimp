"""최종 선정(E). 직선거리 상위 M개 후보 병원을 LLM에 넣어 병원 N개의 순위와 추천 사유 템플릿을 정한다.

- 프롬프트 파일(prompts/<버전>.md)과 LLM 입력 객체, 출력 스키마는 환자 상태 판단(classification/patient_assessment.py)과
  같은 방식으로 만든다. 시스템 프롬프트는 모듈을 import할 때 읽고 채운다. 파일이 없거나 자리표시자가 틀리면 import가
  실패하므로 앱이 기동되지 않는다.
- 추천 개수 N은 요청마다 다를 수 있으므로 시스템 프롬프트가 아니라 LLM 입력 객체에 넣는다.
- LLM은 병원마다 추천 사유 템플릿 id만 고르고, 사유 문장은 reasons.render가 채운다(PRD_v0.1.md F-08 2항).
- LLM 출력은 짧게 만든다. 출력 길이가 응답 시간을 좌우하기 때문이다. 2026-10-30 로컬 vLLM, 수원 개발서버 후보 M=15·N=10에서
  사유를 {template, quote} 객체로 받고 들여쓴 JSON으로 출력하게 했을 때 출력 1,187토큰에 5.1초(제한 시간 5초)가 걸렸다.
  그래서 다음 세 가지로 바꿔 출력 약 290토큰, 1.6초가 되었다.
    - 병원을 병원 ID 대신 후보 번호(no)로 고르게 한다. 병원 ID(예: A2100175)를 옮겨 쓰다 한 자리를 틀린 출력도 있었다.
    - 사유는 템플릿 id 목록으로 받고, 비고 인용은 병원마다 remark_quote 하나로 받는다. 인용은 remark 템플릿에만 쓴다.
    - 프롬프트에서 JSON을 줄바꿈과 들여쓰기 없이 한 줄로 출력하게 한다.
- 우회 여부는 코드가 직선거리로 판정한다. LLM이 직선거리를 빼고 비교하지 않도록, 1순위로 두면 우회가 되는 후보에
  "우회" 태그를 붙여 넣는다. LLM은 그 태그가 붙은 병원을 1순위로 둘 때 우회 사유를 고른다.
- 출력 검증(PRD_v0.1.md F-08 3항)이 실패하면 LlmFailure.VALIDATION_FAILED를 반환한다. 호출한 쪽은 LLM 호출 실패와
  같이 최종 선정 fallback으로 응답한다.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from string import Template
from typing import Any

from pydantic import BaseModel, ConfigDict

from aimp.api.request import Patient
from aimp.classification import patient_assessment
from aimp.common.settings import settings
from aimp.domain.hospital import CongestionStatus
from aimp.domain.types import SEVERE_DISEASE_NAMES, Department, HospitalCategory, PatientCategory
from aimp.engines.capability import CandidateHospital
from aimp.ports.llm import ChatMessage, LlmClient, LlmFailure
from aimp.selection.reasons import PatientContext, ReasonTemplate, render

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# 후보의 태그. "병상 정보 오래됨"·"분만 가능"은 진료 역량 규칙 엔진이, "우회"는 이 모듈이 붙인다
STALE_TAG = "병상 정보 오래됨"
DELIVERY_TAG = "분만 가능"
DETOUR_TAG = "우회"


# 우회 사유. PRD_v0.1.md F-08 '우회 판정 기준'이 정한 4개다. docstring은 출력 스키마에 들어가 프롬프트에 보인다
class DetourReason(StrEnum):
    """우회 사유."""

    BED_AVAILABILITY = "가용병상 여건"
    DEPARTMENT_FIT = "진료과 적합성"
    PATIENT_PREFERENCE = "환자 희망"
    REJECTION_HISTORY = "거절 이력"


# 최종 선정 LLM의 출력 스키마. docstring은 JSON 스키마의 description이 되어 프롬프트에 들어간다.
# 필드에 기본값을 두지 않아 JSON 스키마의 required에 모든 키가 들어가게 한다(PatientAssessment와 같다).
# 순위 필드를 따로 두지 않고 목록 순서를 순위로 쓴다. 순위 값이 목록 순서와 어긋나는 출력을 검증할 필요가 없고 출력도 짧다.
class SelectedHospital(BaseModel):
    """추천 병원 하나. candidate_no는 candidates의 no다. remark_quote는 reasons에 remark가 있을 때 비고에서 그대로 옮긴 문구이고, 없으면 null이다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_no: int
    reasons: tuple[ReasonTemplate, ...]
    remark_quote: str | None


class FinalSelection(BaseModel):
    """최종 선정 결과. recommendations는 1순위부터 놓는다. detour_reason은 1순위 병원에 "우회" 태그가 있을 때만 고르고, 없으면 null이다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendations: tuple[SelectedHospital, ...]
    detour_reason: DetourReason | None


def _render_system_prompt(version: str) -> str:
    template = Template((PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8"))
    return template.substitute(
        detour_reasons="\n".join(f"- {reason}" for reason in DetourReason),
        output_schema=json.dumps(FinalSelection.model_json_schema(), ensure_ascii=False),
    )


SYSTEM_PROMPT = _render_system_prompt(settings.prompt_version)


@dataclass(frozen=True)
class Recommendation:
    """검증을 통과한 추천 병원 하나. reasons는 채운 사유 문장이고, ETA를 구한 뒤 reasons.join_reasons로 잇는다."""

    candidate: CandidateHospital
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SelectionResult:
    """최종 선정 결과. recommendations는 1순위부터 놓는다. 우회가 아니면 detour_reason은 None이다."""

    recommendations: tuple[Recommendation, ...]
    detour: bool
    detour_reason: DetourReason | None


def is_detour(first: CandidateHospital, candidates: Sequence[CandidateHospital]) -> bool:
    """1순위 병원의 직선거리가 후보 중 가장 짧은 직선거리보다 detour_threshold_km 넘게 멀면 True.

    직선거리는 소수 첫째 자리 값이라 빼기의 부동소수점 오차(7.2 - 4.2 = 3.0000000000000004)로 차이가 기준과 같은데
    우회가 되지 않도록, 차이를 소수 여섯째 자리에서 반올림해 비교한다.
    """
    nearest = min(candidate.hospital.distance_km for candidate in candidates)
    return round(first.hospital.distance_km - nearest, 6) > settings.detour_threshold_km


def _remark(patient: Patient) -> str | None:
    """비고 원문. 비었거나 공백뿐이면 None이다."""
    return patient.remark if patient.remark and patient.remark.strip() else None


def _candidate_input(
    no: int, candidate: CandidateHospital, candidates: Sequence[CandidateHospital], context: PatientContext
) -> dict[str, Any]:
    hospital = candidate.hospital
    assessment = context.assessment
    # 진료과는 환자의 필수·보조 진료과 중 병원이 가진 것만 넣는다. 병원의 진료과를 모두 넣으면 입력이 길어진다
    patient_depts = set(assessment.required_depts + assessment.supportive_depts) if assessment else set()
    code = assessment.severe_disease_code if assessment else None
    acceptance = hospital.disease_acceptance.get(code) if code else None
    icu_counts = [beds.available for beds in hospital.icu_beds.values() if beds.available is not None]
    tags = [
        tag
        for tag, on in (
            (STALE_TAG, candidate.stale_beds),
            (DELIVERY_TAG, candidate.can_deliver),
            (DETOUR_TAG, is_detour(candidate, candidates)),
        )
        if on
    ]
    data = {
        "no": no,  # LLM은 병원 ID 대신 이 번호로 병원을 고른다(모듈 docstring)
        "name": hospital.name,
        "categories": [category for category in HospitalCategory if category in hospital.categories],
        "distance_km": hospital.distance_km,
        "er_beds": hospital.er_beds.available,
        "icu_beds": sum(icu_counts) if icu_counts else None,  # 값이 있는 병상 종류의 합(reasons의 icu_beds와 같다)
        "congestion": hospital.congestion_status if hospital.congestion_status != CongestionStatus.NO_DATA else None,
        "departments": [dept for dept in Department if dept in patient_depts and dept in hospital.departments],
        "severe_disease_acceptance": acceptance.status if acceptance else None,  # 환자의 중증응급질환 코드만
        "block_messages": list(hospital.block_messages),
        "tags": tags,
    }
    return {key: value for key, value in data.items() if value not in (None, [])}


def build_input(
    patient: Patient,
    context: PatientContext,
    category: PatientCategory,
    candidates: Sequence[CandidateHospital],
    recommend_count: int,
) -> dict[str, Any]:
    """LLM 입력 객체. 키는 snake_case이고, 값이 없는(null이거나 빈 목록인) 키는 뺀다. 후보 번호(no)는 candidates의 1부터 시작하는 순번이다.

    환자 상태는 환자 상태 판단의 입력 객체에서 비고와 임산부 정보를 뺀 것이다. 비고는 따로 remark 키로 넣고,
    임산부에게 필요한 분만 자원은 후보의 "분만 가능" 태그로 넣는다.
    """
    patient_data = patient_assessment.build_input(patient)
    patient_data.pop("remark", None)
    patient_data.pop("pregnancy_info", None)
    data = {
        "patient": patient_data,
        "assessment": _assessment_input(context),
        "category": category,
        "level": context.condition.level,
        "recommend_count": recommend_count,
        "candidates": [
            _candidate_input(no, candidate, candidates, context) for no, candidate in enumerate(candidates, start=1)
        ],
        "remark": _remark(patient),
    }
    return {key: value for key, value in data.items() if value is not None}


def _assessment_input(context: PatientContext) -> dict[str, Any] | None:
    """환자 상태 판단 결과. 판단이 실패했으면 None이다."""
    assessment = context.assessment
    if assessment is None:
        return None
    code = assessment.severe_disease_code
    data = {
        "is_trauma": assessment.is_trauma,
        "required_depts": list(assessment.required_depts),
        "supportive_depts": list(assessment.supportive_depts),
        "severe_disease": SEVERE_DISEASE_NAMES[code] if code else None,
    }
    return {key: value for key, value in data.items() if value not in (None, [])}


def build_messages(
    patient: Patient,
    context: PatientContext,
    category: PatientCategory,
    candidates: Sequence[CandidateHospital],
    recommend_count: int,
) -> list[ChatMessage]:
    """[system 메시지, user 메시지]. user 메시지는 LLM 입력 객체를 JSON으로 바꾼 문자열이다."""
    data = build_input(patient, context, category, candidates, recommend_count)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False, indent=2)},
    ]


def validate(
    output: FinalSelection,
    candidates: Sequence[CandidateHospital],
    recommend_count: int,
    category: PatientCategory,
    remark: str | None,
) -> str | None:
    """출력 검증(PRD_v0.1.md F-08 3항). 통과하면 None, 실패하면 실패 이유를 반환한다.

    추천 개수는 N개이고, 후보가 N개보다 적으면 후보 수다(2026-10-30 결정).
    템플릿 id가 목록에 있는지는 출력 스키마가 제한하므로 여기서 보지 않는다.
    """
    numbers = [selected.candidate_no for selected in output.recommendations]
    unknown = [no for no in numbers if not 1 <= no <= len(candidates)]
    if unknown:
        return f"후보에 없는 번호 {unknown}"
    if len(set(numbers)) != len(numbers):
        return f"중복된 번호 {numbers}"
    expected = min(recommend_count, len(candidates))
    if len(numbers) != expected:
        return f"추천 개수 {len(numbers)}, 기대 개수 {expected}"
    if is_detour(candidates[numbers[0] - 1], candidates):
        if category == PatientCategory.CARDIAC_ARREST:
            return f"심폐정지 환자의 1순위 {numbers[0]}번이 우회"
        if output.detour_reason is None:
            return f"1순위 {numbers[0]}번이 우회인데 우회 사유 없음"
    for selected in output.recommendations:
        quote = selected.remark_quote
        if quote and (remark is None or quote not in remark):
            return f"{selected.candidate_no}번의 비고 인용 문구가 비고 원문에 없음"
    return None


def _fill_reasons(
    selected: SelectedHospital, candidate: CandidateHospital, context: PatientContext
) -> tuple[str, ...]:
    """LLM이 고른 순서대로 템플릿을 채운다. 채울 값이 없는 템플릿은 버리고, 같은 문장은 한 번만 넣는다.

    남은 사유가 하나도 없으면 distance 사유를 넣는다. distance는 항상 채울 수 있다(2026-10-30 결정).
    """
    filled = [render(template, candidate, context, selected.remark_quote) for template in selected.reasons]
    parts = tuple(dict.fromkeys(reason for reason in filled if reason is not None))
    return parts or (render(ReasonTemplate.DISTANCE, candidate, context),)


def select(
    patient: Patient,
    context: PatientContext,
    category: PatientCategory,
    candidates: Sequence[CandidateHospital],
    recommend_count: int,
    llm_client: LlmClient,
) -> SelectionResult | LlmFailure:
    """최종 선정. LLM 호출이 실패하거나 출력 검증이 실패하면 실패 사유를 반환한다.

    candidates는 도착시간·거리 규칙 엔진이 고른 직선거리 상위 M개이고, 비어 있지 않아야 한다.
    우회가 아니면 LLM이 고른 우회 사유는 버린다.
    """
    result = llm_client.invoke(
        build_messages(patient, context, category, candidates, recommend_count),
        FinalSelection,
        settings.llm_timeout_seconds,
    )
    if isinstance(result, LlmFailure):
        logger.warning("최종 선정 실패 reason=%s", result)
        return result
    output = result.parsed
    problem = validate(output, candidates, recommend_count, category, _remark(patient))
    if problem is not None:
        logger.warning("최종 선정 출력 검증 실패 problem=%s", problem)
        return LlmFailure.VALIDATION_FAILED
    picked = [candidates[selected.candidate_no - 1] for selected in output.recommendations]
    recommendations = tuple(
        Recommendation(candidate, _fill_reasons(selected, candidate, context))
        for selected, candidate in zip(output.recommendations, picked, strict=True)
    )
    detour = is_detour(recommendations[0].candidate, candidates)
    return SelectionResult(recommendations, detour, output.detour_reason if detour else None)
