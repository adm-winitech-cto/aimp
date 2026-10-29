"""ETA 계산(F) 인터페이스.

- 시스템은 최종 선정이나 최종 선정 fallback으로 고른 병원 N개에만 ETA를 구한다. 선정 전 단계는 직선거리를 쓴다.
- 구현은 예외를 밖으로 던지지 않는다. 병원 하나의 ETA를 구하지 못하면 그 병원은 병원정보 검색 API가 준 직선거리로 대신하고,
  계산 방식을 STRAIGHT_LINE으로 반환한다. 호출하는 단계는 STRAIGHT_LINE인 병원이 있으면 "ETA 계산 실패(직선거리 대체)" 경고를 넣는다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from aimp.domain.hospital import Hospital


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


def straight_line_eta(hospital: Hospital) -> Eta:
    """ETA 대신 직선거리를 담는다."""
    return Eta(
        hospital_id=hospital.hospital_id,
        method=EtaMethod.STRAIGHT_LINE,
        distance_km=hospital.distance_km,
        travel_seconds=None,
        arrival_at=None,
    )


class EtaProvider(Protocol):
    def estimate(self, longitude: float, latitude: float, hospitals: Sequence[Hospital]) -> list[Eta]:
        """환자 위치(WGS84 경도, 위도)에서 병원마다의 ETA를 hospitals 순서대로 반환한다."""
        ...
