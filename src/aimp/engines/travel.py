"""도착시간·거리 규칙 엔진(C). 후보 병원 중 직선거리가 가까운 병원을 최종 선정 LLM에 넣을 만큼 고른다.

직선거리는 병원정보 검색 API가 준 환자 위치에서의 거리(Hospital.distance_km)다. 선정 전에는 ETA를 쓰지 않는다.
이 엔진이 기준 시간이나 거리로 병원을 걸러내는지는 정해지지 않았다(PRD_v0.1.md §8 '규칙 엔진의 통과 조건').
"""

from collections.abc import Iterable

from aimp.common.settings import settings
from aimp.domain.hospital import Hospital


def nearest(hospitals: Iterable[Hospital], count: int = settings.llm_candidate_count) -> list[Hospital]:
    """직선거리가 가까운 순으로 앞의 count개. 후보가 count개보다 적으면 모두 반환한다.

    API가 직선거리를 소수 첫째 자리까지만 주므로 같은 값이 자주 나온다. 입력 순서와 관계없이 같은 결과를 내도록
    직선거리가 같으면 hospital_id 순으로 놓는다.
    """
    return sorted(hospitals, key=lambda hospital: (hospital.distance_km, hospital.hospital_id))[:count]
