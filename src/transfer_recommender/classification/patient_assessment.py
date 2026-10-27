"""환자 상태 판단(A1). 환자 정보를 LLM에 넣어 외상 여부, 필수·보조 진료과, 중증응급질환 코드, 중증외상 기준 항목을 판단한다.

- 시스템 프롬프트 파일(prompts/<버전>.md)에는 요청마다 바뀌지 않는 지시문만 적는다.
  요청 데이터는 LLM 입력 객체 하나로 모아 JSON으로 바꾼 뒤 user 메시지에 넣는다.
- 템플릿 자리표시자는 string.Template으로 채운다. str.format은 중괄호를 자리표시자로 해석하므로,
  프롬프트에 JSON 예시를 넣으면 오류가 난다.
- 출력 스키마는 PatientAssessment 하나에서만 만든다. vLLM structured outputs는 토큰을 스키마에 맞게 제한할 뿐
  스키마를 모델에게 보여 주지 않으므로, 같은 스키마를 프롬프트에도 넣는다.
- 비고도 LLM 입력에 넣는다. 중증외상 기준 항목인 손상기전과 신체검사 소견이 비고에만 적힐 수 있기 때문이다.
- 시스템 프롬프트는 모듈을 import할 때 읽고 채운다. 파일이 없거나 자리표시자가 틀리면 import가 실패하므로 앱이 기동되지 않는다.
"""

import json
import logging
from pathlib import Path
from string import Template
from typing import Any

from transfer_recommender.api.request import Patient
from transfer_recommender.domain.patient import PatientAssessment
from transfer_recommender.domain.types import (
    INJURY_FINDINGS,
    INJURY_MECHANISMS,
    SEVERE_DISEASE_NAMES,
    SPECIAL_SITUATIONS,
    Department,
    TraumaCriterion,
    WarningCode,
)
from transfer_recommender.llm_client import ChatMessage, LlmClient, LlmFailure
from transfer_recommender.settings import settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _trauma_criteria_list(group: frozenset[TraumaCriterion]) -> str:
    # frozenset은 순서가 없으므로 열거형 정의 순서로 적는다.
    return "\n".join(f"- {criterion}" for criterion in TraumaCriterion if criterion in group)


def _render_system_prompt(version: str) -> str:
    template = Template((PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8"))
    return template.substitute(
        departments="\n".join(f"- {dept}" for dept in Department),
        severe_disease_codes="\n".join(f"- {code}: {name}" for code, name in SEVERE_DISEASE_NAMES.items()),
        injury_findings=_trauma_criteria_list(INJURY_FINDINGS),
        injury_mechanisms=_trauma_criteria_list(INJURY_MECHANISMS),
        special_situations=_trauma_criteria_list(SPECIAL_SITUATIONS),
        # 스키마는 들여쓰기 없이 넣는다. 들여쓰면 내용은 같고 토큰만 약 300개 늘어난다.
        output_schema=json.dumps(PatientAssessment.model_json_schema(), ensure_ascii=False),
    )


SYSTEM_PROMPT = _render_system_prompt(settings.assessment_prompt_version)


def build_input(patient: Patient) -> dict[str, Any]:
    """LLM 입력 객체. 키는 snake_case이고, 값이 없는(null이거나 빈 목록인) 키는 뺀다."""
    data = {
        "pre_ktas": {"level": patient.pre_ktas.level, "assessment_detail": patient.pre_ktas.assessment_detail},
        "age": patient.info.age,
        "sex": patient.info.sex,
        "chief_complaint": patient.chief_complaint,
        "symptoms": patient.symptoms,
        "consciousness_level": patient.consciousness_level,
        "vital_signs": patient.vital_signs.model_dump(mode="json", exclude_none=True) if patient.vital_signs else None,
        "medical_history": [history.model_dump(mode="json", exclude_none=True) for history in patient.medical_history],
        "medications": patient.medications,
        "pregnancy_info": patient.special_info.pregnancy_info,
        "remark": patient.remark,
    }
    return {key: value for key, value in data.items() if value not in (None, [])}


def build_messages(patient: Patient) -> list[ChatMessage]:
    """[system 메시지, user 메시지]. user 메시지는 LLM 입력 객체를 JSON으로 바꾼 문자열이다."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(build_input(patient), ensure_ascii=False, indent=2)},
    ]


def assess(patient: Patient, llm_client: LlmClient, warnings: list[WarningCode]) -> PatientAssessment | None:
    """LLM 호출이 실패하면 "환자 상태 판단 실패" 경고를 warnings에 추가하고 None을 반환한다."""
    result = llm_client.invoke(build_messages(patient), PatientAssessment, settings.assessment_timeout_seconds)
    if isinstance(result, LlmFailure):
        logger.warning("환자 상태 판단 실패 reason=%s", result)
        warnings.append(WarningCode.ASSESSMENT_FAILED)
        return None
    return result.parsed
