"""병원 데이터 조회(C0) 인터페이스."""

from collections.abc import Collection
from typing import Protocol

from aimp.domain.hospital import Hospital
from aimp.domain.types import HospitalCategory


class HospitalLookupError(Exception):
    """병원 데이터 조회가 실패했다. 외부 시스템이 응답하지 않았거나 응답 형식이 예상과 다르다."""


class HospitalRepository(Protocol):
    def find_by_categories(
        self, longitude: float, latitude: float, categories: Collection[HospitalCategory]
    ) -> list[Hospital]:
        """categories 중 하나 이상에 속하는 병원을 시·도 구분 없이 반환한다.

        longitude, latitude는 환자 위치(WGS84)이고, 병원마다 이 위치에서의 직선거리를 담는다.
        categories가 비어 있으면 ValueError, 조회가 실패하면 HospitalLookupError.
        """
        ...
