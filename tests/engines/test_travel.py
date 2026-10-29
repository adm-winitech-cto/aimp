"""도착시간·거리 규칙 엔진(C) 테스트. PRD_v0.1.md F-15 '도착시간·거리 규칙 엔진'의 완료조건(직선거리 순 정렬, 상위 M개 선택)을 확인한다."""

from aimp.common.settings import settings
from aimp.domain.hospital import BedCount, CongestionStatus, Hospital
from aimp.engines import travel

NO_BEDS = BedCount(available=None, total=None)


def _hospital(hospital_id: str, distance_km: float) -> Hospital:
    return Hospital(
        hospital_id=hospital_id,
        name=hospital_id,
        longitude=127.0,
        latitude=37.0,
        distance_km=distance_km,
        categories=frozenset(),
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


def _ids(hospitals: list[Hospital]) -> list[str]:
    return [hospital.hospital_id for hospital in hospitals]


def test_nearest_sorts_by_distance_and_keeps_count():
    """직선거리가 가까운 순으로 정렬해 앞의 count개만 반환하는지 확인한다."""
    hospitals = [_hospital("A", 12.3), _hospital("B", 0.8), _hospital("C", 30.0), _hospital("D", 5.1)]

    assert _ids(travel.nearest(hospitals, count=3)) == ["B", "D", "A"]


def test_nearest_returns_all_when_fewer_than_count():
    """후보가 count개보다 적으면 모두 직선거리 순으로 반환하는지 확인한다."""
    hospitals = [_hospital("A", 2.0), _hospital("B", 1.0)]

    assert _ids(travel.nearest(hospitals, count=15)) == ["B", "A"]


def test_nearest_returns_empty_for_no_candidates():
    assert travel.nearest([], count=15) == []


def test_nearest_breaks_distance_ties_by_hospital_id():
    """직선거리가 같으면 입력 순서와 관계없이 hospital_id 순으로 놓는지 확인한다. 경계에서 잘리는 병원도 같아야 한다."""
    hospitals = [_hospital("C", 3.2), _hospital("A", 3.2), _hospital("D", 1.0), _hospital("B", 3.2)]

    assert _ids(travel.nearest(hospitals, count=3)) == ["D", "A", "B"]
    assert _ids(travel.nearest(list(reversed(hospitals)), count=3)) == ["D", "A", "B"]


def test_nearest_uses_llm_candidate_count_by_default():
    """count를 주지 않으면 config/settings.yaml의 llm_candidate_count(M)개를 고르는지 확인한다."""
    hospitals = [_hospital(f"H{i:03d}", float(i)) for i in range(settings.llm_candidate_count + 5)]

    result = travel.nearest(hospitals)

    assert _ids(result) == [f"H{i:03d}" for i in range(settings.llm_candidate_count)]
