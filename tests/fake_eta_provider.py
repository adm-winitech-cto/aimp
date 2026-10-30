"""테스트용 가짜 EtaProvider."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from aimp.domain.hospital import Hospital
from aimp.ports.eta_provider import Eta, EtaMethod, straight_line_eta


@dataclass
class FakeEtaProvider:
    """병원마다 Tmap ETA API로 구한 것처럼 ETA를 돌려주고, 받은 병원 ID 목록을 calls에 기록한다.
    failing_ids에 있는 병원은 직선거리로 대신한다."""

    failing_ids: frozenset[str] = frozenset()
    calls: list[list[str]] = field(default_factory=list)

    def estimate(self, longitude: float, latitude: float, hospitals: Sequence[Hospital]) -> list[Eta]:
        self.calls.append([hospital.hospital_id for hospital in hospitals])
        return [
            straight_line_eta(hospital)
            if hospital.hospital_id in self.failing_ids
            else Eta(hospital.hospital_id, EtaMethod.TMAP, hospital.distance_km * 1.3, 600, None)
            for hospital in hospitals
        ]
