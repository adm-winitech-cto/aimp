"""ETA. ETA 계산(F)의 출력."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EtaMethod(StrEnum):
    """ETA 계산 방식. 응답에 이 이름으로 표시한다."""

    TMAP = "Tmap ETA API"
    STRAIGHT_LINE = "직선거리 대체"


@dataclass(frozen=True)
class Eta:
    """병원 한 곳의 ETA."""

    hospital_id: str
    method: EtaMethod
    distance_km: float  # TMAP이면 경로 거리, STRAIGHT_LINE이면 병원정보 검색 API가 준 직선거리
    travel_seconds: int | None  # 예상 소요 시간. STRAIGHT_LINE이면 None
    arrival_at: datetime | None  # 도착 예정 시각(KST). STRAIGHT_LINE이면 None
