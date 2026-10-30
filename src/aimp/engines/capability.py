"""진료 역량 규칙 엔진(C). 병원의 진료 역량 조건(PRD_v0.1.md F-13)을 만족하지 않는 병원을 후보에서 뺀다.

가용병상 조건(응급실, 중환자실), 중증응급질환 수용가능 조건, 필수 진료과 조건, 특수 자원 조건을 적용한다.
분만 자원은 병원을 거르지 않고 "분만 가능" 태그로 표시한다.

필수 진료과 조건의 "해당 진료과의 실시간 진료불가 메시지 없음"은 LLM으로 판단한다. 진료불가 메시지는 병원이 쓴 자유
문장이라 진료과 필드가 없기 때문이다(docs/90_domain/er-block-messages.md).
- 프롬프트 파일(prompts/<버전>.md)과 LLM 입력 객체, 출력 스키마는 환자 상태 판단(classification/patient_assessment.py)과
  같은 방식으로 만든다.
- 시스템 프롬프트는 모듈을 import할 때 읽고 채운다. 파일이 없거나 자리표시자가 틀리면 import가 실패하므로
  앱이 기동되지 않는다.
- LLM은 필수 진료과를 막는 메시지와 그 메시지가 적은 시간대만 옮긴다. 지금 그 시간대에 해당하는지는 코드가 판정한다.
  LLM에 지금 시각을 주고 판단하게 했을 때 "평일 9A~6P만 가능"을 평일 16시에 막힌 것으로 판단하는 등 시각 비교를
  자주 틀렸다(2026-10-30 로컬 vLLM).
"""

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from string import Template
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aimp.common.settings import settings
from aimp.domain.hospital import AcceptanceStatus, Hospital
from aimp.domain.patient import PatientAssessment, SevereJudgment
from aimp.domain.types import Department, PatientCategory, Resource, SevereDiseaseCode, WarningCode
from aimp.ports.llm import ChatMessage, LlmClient, LlmFailure

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# 중환자실 가용병상 조건을 적용하는 중증 적용 규칙
SEVERE_CATEGORIES: frozenset[PatientCategory] = frozenset(
    {
        PatientCategory.SEVERE_TRAUMA,
        PatientCategory.SEVERE_NON_TRAUMA,
        PatientCategory.STROKE_SUSPECTED,
        PatientCategory.STROKE_SCREENING_POSITIVE,
    }
)

# mkioskty2(뇌경색 재관류), mkioskty3(거미막하출혈 수술), mkioskty4(기타 뇌출혈 수술)
_STROKE_TREATMENT_CODES = (SevereDiseaseCode.MKIOSKTY2, SevereDiseaseCode.MKIOSKTY3, SevereDiseaseCode.MKIOSKTY4)

# 특수 자원 → 병원이 그 자원을 갖췄는지 판정하는 조건. PRD_v0.1.md F-02 판정 규칙 표의 병원 데이터 열과 같아야 한다.
# 분만은 병원을 거르지 않고 태그로 표시하므로 이 표에 넣지 않는다(_can_deliver).
_RESOURCE_CONDITIONS: dict[Resource, Callable[[Hospital], bool]] = {
    # 셋 중 하나라도 Y
    Resource.STROKE_TREATMENT: lambda hospital: any(_accepts_disease(hospital, c) for c in _STROKE_TREATMENT_CODES),
    # mkioskty1(심근경색 재관류)이 Y
    Resource.MI_REPERFUSION: lambda hospital: _accepts_disease(hospital, SevereDiseaseCode.MKIOSKTY1),
    # API가 소아 응급실 병상(hv28)을 주지 않아 진료과 보유로 판정한다
    Resource.PEDIATRIC_EMERGENCY: lambda hospital: Department.PEDIATRICS in hospital.departments,
}


class Weekday(StrEnum):
    """요일. 정의 순서가 datetime.weekday() 순서(월요일 0)와 같다."""

    MON = "월"
    TUE = "화"
    WED = "수"
    THU = "목"
    FRI = "금"
    SAT = "토"
    SUN = "일"


# 진료불가 메시지 판단 LLM의 출력 스키마. docstring은 JSON 스키마의 description이 되어 프롬프트에 들어간다.
# 필드에 기본값을 두지 않아 JSON 스키마의 required에 모든 키가 들어가게 한다(PatientAssessment와 같다).
# 메시지마다 막힌 진료과를 내게 하면 출력 토큰이 메시지 수만큼 늘어, 개발서버 수원 후보의 메시지(29문장)에서 제한
# 시간 3초를 넘겼다. 진료과를 고른 메시지만 내게 해도 194문장에서 3초를 넘겨서, 필수 진료과만 묻고 그 진료과를
# 막는 메시지만 받는다(2026-10-30 로컬 vLLM).
class TimeWindow(BaseModel):
    """요일과 시각 범위 하나. end가 start보다 이르면 다음 날 end까지다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: tuple[Weekday, ...]
    start: str = Field(pattern=r"^([01][0-9]|2[0-4]):[0-5][0-9]$")  # HH:MM
    end: str = Field(pattern=r"^([01][0-9]|2[0-4]):[0-5][0-9]$")  # HH:MM


class BlockingMessage(BaseModel):
    """필수 진료과의 진료를 막는 메시지 하나와 그 시간 조건."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: int
    # 항상: 시간대가 없다. 시간대 밖: windows는 진료 가능 시간대다. 시간대 안: windows는 진료 불가 시간대다
    when: Literal["항상", "시간대 밖", "시간대 안"]
    windows: tuple[TimeWindow, ...]


class BlockMessageJudgment(BaseModel):
    """진료불가 메시지 판단 결과."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocking_messages: tuple[BlockingMessage, ...]


def _render_system_prompt(version: str) -> str:
    template = Template((PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8"))
    return template.substitute(
        departments="\n".join(f"- {dept}" for dept in Department),
        output_schema=json.dumps(BlockMessageJudgment.model_json_schema(), ensure_ascii=False),
    )


SYSTEM_PROMPT = _render_system_prompt(settings.block_message_prompt_version)


@dataclass(frozen=True)
class CandidateHospital:
    """진료 역량 조건을 통과한 후보 병원 하나."""

    hospital: Hospital
    # "병상 정보 오래됨" 태그. True면 병상 값(er_beds, icu_beds)이 지금과 다를 수 있다. 병상 값은 바꾸지 않고 그대로 둔다
    stale_beds: bool
    # "분만 가능" 태그. 환자에게 분만 자원이 필요하고 병원이 분만이 가능하면 True다. 병원을 거르는 데 쓰지 않는다
    can_deliver: bool = False


def filter_candidates(
    hospitals: Iterable[Hospital],
    severe_judgment: SevereJudgment,
    assessment: PatientAssessment | None,
    category: PatientCategory,
    queried_at: datetime,
    llm_client: LlmClient,
) -> tuple[list[CandidateHospital], list[WarningCode]]:
    """(남은 후보 병원 목록, 경고 목록). 남은 후보는 입력 순서를 유지한다.

    queried_at은 병원정보 조회 시각이다. beds_updated_at(API의 lastUpdatedAt)과 같이 시간대 정보 없는 KST로 준다.
    assessment가 None이면(환자 상태 판단 실패) 중증응급질환 수용가능 조건과 필수 진료과 조건을 적용하지 않는다.
    llm_client는 진료불가 메시지 판단에 쓴다. 필수 진료과가 있고, 다른 조건을 통과한 후보에 메시지가 있을 때만 호출한다.
    특수 자원 조건과 "분만 가능" 태그는 severe_judgment.required_resources로 정하므로 assessment가 None이어도 적용한다.
    """
    # 심폐정지 환자에게는 어떤 조건도 적용하지 않고 "분만 가능" 태그도 붙이지 않는다. A0은 15세 미만이거나 임산부인
    # 심정지 환자에게도 소아 응급 진료나 분만 자원을 붙이므로, required_resources가 아니라 적용 규칙을 보고 건너뛴다
    if category == PatientCategory.CARDIAC_ARREST:
        return [CandidateHospital(hospital, stale_beds=False) for hospital in hospitals], []

    max_age = timedelta(minutes=settings.bed_data_max_age_minutes)
    check_icu = settings.require_icu_beds and category in SEVERE_CATEGORIES
    disease_code = assessment.severe_disease_code if assessment is not None else None
    required_depts = assessment.required_depts if assessment is not None else ()
    resources = severe_judgment.required_resources
    resource_conditions = [condition for resource, condition in _RESOURCE_CONDITIONS.items() if resource in resources]
    needs_delivery = Resource.DELIVERY in resources
    candidates: list[CandidateHospital] = []
    for hospital in hospitals:
        # 중증응급질환 수용가능 조건, 필수 진료과 조건, 특수 자원 조건은 병상 신선도 태그와 관계없이 적용한다
        if disease_code is not None and not _accepts_disease(hospital, disease_code):
            continue
        if not hospital.departments.issuperset(required_depts):  # 필수 진료과 중 하나라도 없는 병원은 뺀다
            continue
        if not all(condition(hospital) for condition in resource_conditions):  # 특수 자원 중 하나라도 없는 병원은 뺀다
            continue
        stale = hospital.beds_updated_at is None or queried_at - hospital.beds_updated_at > max_age
        # 태그가 붙은 병원에는 가용병상 조건을 적용하지 않는다
        if not stale and (not _has_er_beds(hospital) or (check_icu and not _has_icu_beds(hospital))):
            continue
        can_deliver = needs_delivery and _can_deliver(hospital)
        candidates.append(CandidateHospital(hospital, stale_beds=stale, can_deliver=can_deliver))

    if required_depts:
        candidates = _remove_blocked(candidates, frozenset(required_depts), queried_at, llm_client)
    warnings = [WarningCode.STALE_BED_DATA] if any(candidate.stale_beds for candidate in candidates) else []
    return candidates, warnings


def _accepts_disease(hospital: Hospital, code: SevereDiseaseCode) -> bool:
    """중증응급질환 수용가능 값이 Y면 True. 불가능·정보미제공이거나 항목이 없으면 False(PRD F-13의 조건이 "수용가능 = Y"다)."""
    acceptance = hospital.disease_acceptance.get(code)
    return acceptance is not None and acceptance.status == AcceptanceStatus.AVAILABLE


def build_input(sentences: list[str], required_depts: frozenset[Department]) -> dict[str, Any]:
    """LLM 입력 객체. message_id는 sentences의 1부터 시작하는 순번이다. 지금 시각은 넣지 않는다(모듈 docstring)."""
    return {
        "required_depts": [dept for dept in Department if dept in required_depts],  # 열거형 정의 순서
        "messages": [{"message_id": i, "text": sentence} for i, sentence in enumerate(sentences, start=1)],
    }


def build_messages(sentences: list[str], required_depts: frozenset[Department]) -> list[ChatMessage]:
    """[system 메시지, user 메시지]. user 메시지는 LLM 입력 객체를 JSON으로 바꾼 문자열이다."""
    data = build_input(sentences, required_depts)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False, indent=2)},
    ]


def _remove_blocked(
    candidates: list[CandidateHospital],
    required_depts: frozenset[Department],
    queried_at: datetime,
    llm_client: LlmClient,
) -> list[CandidateHospital]:
    """진료불가 메시지가 필수 진료과 중 하나라도 지금 진료할 수 없다고 알리는 병원을 뺀다.

    여러 병원에 같은 문장이 있으면 LLM에는 한 번만 넣는다. 후보에 메시지가 하나도 없으면 LLM을 호출하지 않는다.
    LLM 호출이 실패하면 메시지로 병원을 빼지 않는다. PRD F-13에 이 실패의 경고 코드가 없으므로 경고는 넣지 않는다.
    LLM 출력에 있는 번호 중 입력에 없는 번호는 버린다. 메시지가 적은 시간대는 queried_at으로 판정한다.
    """
    sentences = list(dict.fromkeys(sentence for c in candidates for sentence in c.hospital.block_messages))
    if not sentences:
        return candidates
    result = llm_client.invoke(
        build_messages(sentences, required_depts),
        BlockMessageJudgment,
        settings.block_message_timeout_seconds,
    )
    if isinstance(result, LlmFailure):
        logger.warning("진료불가 메시지 판단 실패 reason=%s", result)
        return candidates
    blocked = {
        sentences[message.message_id - 1]
        for message in result.parsed.blocking_messages
        if 1 <= message.message_id <= len(sentences) and blocks_now(message, queried_at)
    }
    return [candidate for candidate in candidates if blocked.isdisjoint(candidate.hospital.block_messages)]


def blocks_now(message: BlockingMessage, at: datetime) -> bool:
    """at에 메시지가 필수 진료과를 막으면 True. 공휴일은 알 수 없으므로 요일로만 판정한다."""
    if message.when == "항상":
        return True
    inside = any(_in_window(window, at) for window in message.windows)
    return not inside if message.when == "시간대 밖" else inside


def _in_window(window: TimeWindow, at: datetime) -> bool:
    """at이 시간대 안이면 True. 시작 시각은 포함하고 끝 시각은 포함하지 않는다.

    end가 start보다 이르면(예: 18:00~09:00) 그 요일 start부터 다음 날 end까지다.
    """
    weekdays = list(Weekday)
    today, yesterday = weekdays[at.weekday()], weekdays[at.weekday() - 1]
    now, start, end = at.hour * 60 + at.minute, _minutes(window.start), _minutes(window.end)
    if start <= end:
        return today in window.days and start <= now < end
    return (today in window.days and now >= start) or (yesterday in window.days and now < end)


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _can_deliver(hospital: Hospital) -> bool:
    """mkioskty16(분만) 수용가능 값이 Y이거나 분만실이 가용이면 True. PRD_v0.1.md F-02 판정 규칙 표의 분만 행."""
    return _accepts_disease(hospital, SevereDiseaseCode.MKIOSKTY16) or hospital.delivery_room is True


def _has_er_beds(hospital: Hospital) -> bool:
    """응급실 가용병상이 1 이상이거나 API가 값을 주지 않았으면 True."""
    available = hospital.er_beds.available
    return available is None or available > 0


def _has_icu_beds(hospital: Hospital) -> bool:
    """중환자실 병상 종류 중 하나라도 가용병상이 1 이상이거나, API가 모든 종류의 값을 주지 않았으면 True."""
    counts = [beds.available for beds in hospital.icu_beds.values()]
    return any(count is not None and count > 0 for count in counts) or all(count is None for count in counts)
