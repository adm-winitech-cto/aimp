"""최종 선정 fallback(PRD_v0.1.md F-09). 최종 선정 LLM이 실패하면 LLM을 거치지 않고 후보 병원을 직선거리 순으로 N개 고른다.

- 추천 사유는 최종 선정과 같은 템플릿(reasons.py) 중 정해진 목록(FALLBACK_TEMPLATES)을 채워 만든다.
- 결과는 최종 선정과 같은 Recommendation이다. ETA는 선정이 끝난 뒤 구하므로, 처리 흐름이 reasons.join_reasons로 잇는다.
"""

from collections.abc import Iterable

from aimp.domain.types import WarningCode
from aimp.engines import travel
from aimp.engines.capability import CandidateHospital
from aimp.selection.final_selection import Recommendation
from aimp.selection.reasons import PatientContext, ReasonTemplate, render

# 추천 사유에 넣는 템플릿. 이 순서로 채운다
FALLBACK_TEMPLATES = (ReasonTemplate.GRADE, ReasonTemplate.DISTANCE, ReasonTemplate.ER_BEDS)


def select(
    candidates: Iterable[CandidateHospital],
    count: int,
    patient: PatientContext,
    remark: str | None,
    warnings: list[WarningCode],
) -> tuple[Recommendation, ...]:
    """직선거리가 가까운 순으로 앞의 count개. 직선거리가 같으면 hospital_id 순이다.

    사유는 FALLBACK_TEMPLATES를 이 순서로 채운 것이고, 채울 값이 없는 템플릿은 뺀다.
    비고(remark)가 있으면(공백뿐이면 없음) 반영하지 못하므로 warnings에 "비고 미반영" 경고를 넣는다.
    """
    if remark and remark.strip():
        warnings.append(WarningCode.REMARK_NOT_APPLIED)
    return tuple(
        Recommendation(candidate, _reasons(candidate, patient)) for candidate in travel.nearest(candidates, count)
    )


def _reasons(candidate: CandidateHospital, patient: PatientContext) -> tuple[str, ...]:
    filled = (render(template, candidate, patient) for template in FALLBACK_TEMPLATES)
    return tuple(reason for reason in filled if reason is not None)
