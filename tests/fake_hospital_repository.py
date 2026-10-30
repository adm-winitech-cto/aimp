"""테스트용 가짜 HospitalRepository."""

from collections.abc import Collection
from dataclasses import dataclass, field

from aimp.domain.hospital import BedCount, CongestionStatus, Hospital
from aimp.domain.types import HospitalCategory

NO_BEDS = BedCount(available=None, total=None)


def make_hospital(hospital_id: str, distance_km: float, *categories: HospitalCategory) -> Hospital:
    """처리 흐름 테스트에 필요한 값(병원 ID, 직선거리, 병원 분류)만 채운 병원. 병원명은 '<병원 ID>병원'이다."""
    return Hospital(
        hospital_id=hospital_id,
        name=f"{hospital_id}병원",
        longitude=128.6,
        latitude=35.9,
        distance_km=distance_km,
        categories=frozenset(categories),
        departments=frozenset(),
        er_beds=NO_BEDS,
        icu_beds={},
        operating_room_beds=NO_BEDS,
        ward_beds=NO_BEDS,
        resuscitation_room=NO_BEDS,
        beds_updated_at=None,
        congestion=None,
        congestion_status=CongestionStatus.NO_DATA,
        disease_acceptance={},
        equipment={},
        delivery_room=None,
        block_messages=(),
    )


@dataclass
class FakeHospitalRepository:
    """정해 둔 병원 중 받은 병원 분류에 하나 이상 속하는 병원을 직선거리 순으로 돌려주고, 받은 병원 분류를 calls에 기록한다."""

    hospitals: list[Hospital]
    calls: list[frozenset[HospitalCategory]] = field(default_factory=list)

    def find_by_categories(
        self, longitude: float, latitude: float, categories: Collection[HospitalCategory]
    ) -> list[Hospital]:
        self.calls.append(frozenset(categories))
        found = [hospital for hospital in self.hospitals if hospital.categories & frozenset(categories)]
        return sorted(found, key=lambda hospital: hospital.distance_km)


def default_repository() -> FakeHospitalRepository:
    """병원 분류마다 병원이 하나 이상 있는 가짜 HospitalRepository."""
    return FakeHospitalRepository(
        [
            make_hospital(
                "REC", 8.0, HospitalCategory.REGIONAL_EMERGENCY_CENTER, HospitalCategory.REGIONAL_TRAUMA_CENTER
            ),
            make_hospital("LEC", 3.0, HospitalCategory.LOCAL_EMERGENCY_CENTER),
            make_hospital("LEI1", 1.5, HospitalCategory.LOCAL_EMERGENCY_INSTITUTION),
            make_hospital("LEI2", 4.2, HospitalCategory.LOCAL_EMERGENCY_INSTITUTION),
        ]
    )
