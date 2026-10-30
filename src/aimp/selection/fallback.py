"""최종 선정 fallback(PRD_v0.1.md F-09). LLM을 거치지 않고 후보 병원을 직선거리 순으로 N개 고른다.

- 최종 선정 LLM이 실패했을 때 쓴다. 최종 선정 LLM을 연결하기 전(#18)에는 pipeline.py가 최종 선정 대신 이 모듈을 부른다.
- 추천 사유는 최종 선정과 같은 템플릿(reasons.py) 중 정해진 목록(FALLBACK_TEMPLATES)을 채워 만든다.
- ETA는 선정이 끝난 뒤 추천 병원에만 구하므로, 병원 선정(select)과 사유 문장(reason)을 나눈다.
"""

from collections.abc import Iterable

from aimp.domain.eta import Eta
from aimp.domain.types import WarningCode
from aimp.engines import travel
from aimp.engines.capability import CandidateHospital
from aimp.selection.reasons import PatientContext, ReasonTemplate, join_reasons, render

# 추천 사유에 넣는 템플릿. 이 순서로 채운다
FALLBACK_TEMPLATES = (ReasonTemplate.GRADE, ReasonTemplate.DISTANCE, ReasonTemplate.ER_BEDS)


def select(
    candidates: Iterable[CandidateHospital], count: int, remark: str | None, warnings: list[WarningCode]
) -> list[CandidateHospital]:
    """직선거리가 가까운 순으로 앞의 count개. 직선거리가 같으면 hospital_id 순이다.

    비고(remark)가 있으면 반영하지 못하므로 warnings에 "비고 미반영" 경고를 넣는다.
    """
    if remark:
        warnings.append(WarningCode.REMARK_NOT_APPLIED)
    return travel.nearest(candidates, count)


def reason(candidate: CandidateHospital, patient: PatientContext, eta: Eta) -> str:
    """추천 사유 문장. 채울 값이 없는 템플릿은 빼고, Tmap ETA API로 ETA를 구했으면 도착 예정 시간을 붙인다."""
    return join_reasons((render(template, candidate, patient) for template in FALLBACK_TEMPLATES), eta)
