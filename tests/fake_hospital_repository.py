"""테스트용 가짜 HospitalRepository."""

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime

from aimp.domain.hospital import AcceptanceStatus, BedCount, CongestionStatus, DiseaseAcceptance, Hospital
from aimp.domain.types import Department, HospitalCategory, SevereDiseaseCode
from aimp.pipeline import KST

NO_BEDS = BedCount(available=None, total=None)


def make_hospital(
    hospital_id: str,
    distance_km: float,
    *categories: HospitalCategory,
    er_available: int | None = None,
    stale: bool = False,
) -> Hospital:
    """처리 흐름 테스트에 필요한 값(병원 ID, 직선거리, 병원 분류)을 채운 병원. 병원명은 '<병원 ID>병원'이다.

    진료 역량 규칙 엔진이 거르지 않도록 모든 진료과를 갖추고 모든 중증질환을 수용할 수 있다.
    er_available은 응급실 가용병상 수이고, None이면 API가 값을 주지 않은 병원이다.
    stale이 False면 병상 갱신 시각이 지금이고, True면 갱신 시각이 없다("병상 정보 오래됨" 태그가 붙는다).
    """
    return Hospital(
        hospital_id=hospital_id,
        name=f"{hospital_id}병원",
        longitude=128.6,
        latitude=35.9,
        distance_km=distance_km,
        categories=frozenset(categories),
        departments=frozenset(Department),
        er_beds=BedCount(available=er_available, total=None),
        icu_beds={},
        operating_room_beds=NO_BEDS,
        ward_beds=NO_BEDS,
        resuscitation_room=NO_BEDS,
        beds_updated_at=None if stale else datetime.now(KST).replace(tzinfo=None),
        congestion=None,
        congestion_status=CongestionStatus.NO_DATA,
        disease_acceptance={code: DiseaseAcceptance(AcceptanceStatus.AVAILABLE, None) for code in SevereDiseaseCode},
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
