"""병원 데이터 조회(C0) 인터페이스."""

from collections.abc import Collection
from typing import Protocol

from transfer_recommender.domain.hospital import Hospital, HospitalCategory


class HospitalRepository(Protocol):
    def find_by_categories(self, categories: Collection[HospitalCategory]) -> list[Hospital]:
        """categories 중 하나 이상에 속하는 병원을 시·도 구분 없이 반환한다. categories가 비어 있으면 ValueError."""
        ...
