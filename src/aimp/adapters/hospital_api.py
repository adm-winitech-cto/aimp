"""HospitalRepository의 병원정보 검색 API 구현. 병원 데이터 조회(C0)가 쓴다.

- 응급실 목록(/emergency-rooms)을 환자 위치에서 반경 안으로 조회해 후보 병원, 직선거리, 혼잡도를 받는다.
- API에 권역외상센터 분류가 없어서, 권역외상센터는 config/trauma_centers.yaml의 hpid 목록으로 정한다.
  권역외상센터는 시·도와 관계없이 가장 가까운 곳을 찾아야 하므로 반경 없이 전국 응급실 목록에서 고른다.
- 중증질환 수용가능 여부와 진료과목은 병원 상세(/{id})에만 있으므로, 후보 병원마다 병원 상세를 병렬로 호출한다.
- 인증 키는 환경 변수 HOSPITAL_API_CLIENT_ID, HOSPITAL_API_KEY에서 읽는다. 키를 설정 파일과 저장소에 넣지 않는다.
- API 응답 필드와 Hospital 필드의 대응은 domain/hospital.py의 docstring에 있다.
"""

import logging
import os
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict

from aimp.common.settings import CONFIG_DIR, load_yaml, settings
from aimp.domain.hospital import (
    AcceptanceStatus,
    BedCount,
    CongestionStatus,
    DiseaseAcceptance,
    Equipment,
    Hospital,
    IcuBedType,
)
from aimp.domain.types import HospitalCategory
from aimp.ports.hospital_repository import HospitalLookupError

logger = logging.getLogger(__name__)

# 응급실 목록의 emergencyClasses 검색 조건 값. API에는 권역외상센터 분류가 없다.
_EMERGENCY_CLASSES = {
    HospitalCategory.REGIONAL_EMERGENCY_CENTER: "REGIONAL_CENTER",
    HospitalCategory.LOCAL_EMERGENCY_CENTER: "LOCAL_CENTER",
    HospitalCategory.LOCAL_EMERGENCY_INSTITUTION: "LOCAL_INSTITUTION",
}
_PAGE_SIZE = 100  # 목록 API가 받는 최대 페이지 크기

# 병원 상세 availableBeds[]의 key
_ER_BED_KEY = "hvec"
_ICU_BED_KEYS = {
    IcuBedType.GENERAL: "hvicc",
    IcuBedType.NEUROLOGY: "hvcc",
    IcuBedType.THORACIC_SURGERY: "hvccc",
    IcuBedType.NEONATAL: "hvncc",
}
_OPERATING_ROOM_KEY = "hvoc"
_WARD_KEY = "hvgc"
_EQUIPMENT_KEYS = {
    Equipment.CT: "hvctayn",
    Equipment.MRI: "hvmriayn",
    Equipment.ANGIOGRAPHY: "hvangioayn",
    Equipment.VENTILATOR: "hvventiayn",
    Equipment.PREMATURE_VENTILATOR: "hvventisoayn",
    Equipment.INCUBATOR: "hvincuayn",
    Equipment.CRRT: "hvcrrtayn",
    Equipment.ECMO: "hvecmoayn",
    Equipment.HYPERBARIC_OXYGEN: "hvoxyayn",
    Equipment.HYPOTHERMIA: "hvhypoayn",
    Equipment.AMBULANCE: "hvamyn",
}
_DELIVERY_ROOM_KEY = "hv42"
_NO_BEDS = BedCount(available=None, total=None)


class _TraumaCenters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    regional_trauma_centers: dict[str, str]  # hpid: 병원명


def load_trauma_center_ids(path: Path) -> frozenset[str]:
    """권역외상센터 목록 파일을 읽어 hpid 집합을 반환한다. 형식이 틀리면 ValueError(pydantic ValidationError 포함)."""
    return frozenset(_TraumaCenters.model_validate(load_yaml(path)).regional_trauma_centers)


# 모듈을 import할 때 읽는다. 형식이 틀리면 import가 실패한다.
TRAUMA_CENTER_IDS = load_trauma_center_ids(CONFIG_DIR / "trauma_centers.yaml")


class HospitalApiRepository:
    """병원정보 검색 API로 병원을 조회하는 HospitalRepository 구현.

    - 요청마다 timeout(초)을 건다. 재시도하지 않는다.
    - 호출이 하나라도 실패하거나 응답 형식이 예상과 다르면 HospitalLookupError를 낸다. 일부 병원만 빼고 반환하면
      가장 가까운 병원이 후보에서 빠져도 알 수 없기 때문이다.
    """

    def __init__(
        self,
        url: str = settings.hospital_api_url,
        timeout: float = settings.hospital_api_timeout_seconds,
        max_concurrency: int = settings.hospital_api_max_concurrency,
        radius_km: float = settings.hospital_search_radius_km,
        trauma_center_ids: Collection[str] = TRAUMA_CENTER_IDS,
        client_id: str | None = None,
        api_key: str | None = None,
    ):
        client_id = client_id or os.environ.get("HOSPITAL_API_CLIENT_ID")
        api_key = api_key or os.environ.get("HOSPITAL_API_KEY")
        if not client_id or not api_key:
            raise ValueError("환경 변수 HOSPITAL_API_CLIENT_ID, HOSPITAL_API_KEY가 없습니다")
        self._url = url
        self._timeout = timeout
        self._max_concurrency = max_concurrency
        self._radius_km = radius_km
        self._trauma_center_ids = frozenset(trauma_center_ids)
        self._session = requests.Session()
        # 제공처가 안내한 대로 프록시를 거치지 않는다. trust_env를 끄면 환경 변수의 프록시 설정을 쓰지 않는다.
        self._session.trust_env = False
        self._session.headers.update(
            {"X-GGFI-Client-Id": client_id, "X-GGFI-API-Key": api_key, "Accept": "application/json"}
        )

    def find_by_categories(
        self, longitude: float, latitude: float, categories: Collection[HospitalCategory]
    ) -> list[Hospital]:
        if not categories:
            raise ValueError("categories가 비어 있습니다")
        location = {"longitude": longitude, "latitude": latitude}
        rooms: list[dict[str, Any]] = []
        classes = [_EMERGENCY_CLASSES[c] for c in categories if c in _EMERGENCY_CLASSES]
        if classes:
            rooms = self._emergency_rooms(
                {**location, "radiusKm": self._radius_km, "emergencyClasses": ",".join(classes)}
            )
        if HospitalCategory.REGIONAL_TRAUMA_CENTER in categories:
            found = {room["id"] for room in rooms}
            rooms += [room for room in self._trauma_center_rooms(location) if room["id"] not in found]

        with ThreadPoolExecutor(max_workers=self._max_concurrency) as pool:
            details = list(pool.map(lambda room: self._get(f"/{room['id']}", location), rooms))
        try:
            hospitals = [_to_hospital(room, detail, self._trauma_center_ids) for room, detail in zip(rooms, details)]
            hospitals.sort(key=lambda hospital: hospital.distance_km)
        except (KeyError, TypeError, ValueError) as e:
            raise HospitalLookupError("병원정보 검색 API 응답 형식이 예상과 다릅니다") from e
        return hospitals

    def _trauma_center_rooms(self, location: dict[str, float]) -> list[dict[str, Any]]:
        """반경 없이 전국 응급실 목록을 읽어 권역외상센터만 고른다."""
        if not self._trauma_center_ids:
            logger.warning("권역외상센터 목록(config/trauma_centers.yaml)이 비어 있어 권역외상센터를 찾지 못한다")
            return []
        rooms = [room for room in self._emergency_rooms(location) if room["id"] in self._trauma_center_ids]
        missing = self._trauma_center_ids - {room["id"] for room in rooms}
        if missing:
            logger.warning("응급실 목록에 없는 권역외상센터 hpid가 있다 hpids=%s", sorted(missing))
        return rooms

    def _emergency_rooms(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """응급실 목록의 모든 페이지를 읽는다."""
        rooms: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._get("/emergency-rooms", {**params, "page": page, "pageSize": _PAGE_SIZE})
            rooms += data["items"]
            if not data["items"] or len(rooms) >= data["totalCount"]:
                return rooms
            page += 1

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        """API를 호출하고 응답의 data를 반환한다."""
        try:
            resp = self._session.get(self._url + path, params=params, timeout=self._timeout)
            resp.raise_for_status()
            body = resp.json()
        except (requests.RequestException, ValueError) as e:
            # 제공처에 서버 오류를 물을 때 응답 헤더 X-Request-Id가 필요하다.
            request_id = e.response.headers.get("X-Request-Id") if getattr(e, "response", None) is not None else None
            raise HospitalLookupError(f"병원정보 검색 API 호출 실패 path={path} request_id={request_id}") from e
        if body.get("result") != "SUCCESS":
            raise HospitalLookupError(f"병원정보 검색 API 호출 실패 path={path} result={body.get('result')}")
        return body["data"]


def _to_hospital(room: dict[str, Any], detail: dict[str, Any], trauma_center_ids: frozenset[str]) -> Hospital:
    """응급실 목록의 항목 하나와 그 병원의 병원 상세를 Hospital로 바꾼다."""
    beds = {b["key"]: BedCount(available=b["availableCount"], total=b["totalCount"]) for b in detail["availableBeds"]}
    equipment = {e["key"]: e["available"] for e in detail["availableEquipment"]}
    facilities = {f["key"]: f["available"] for f in detail["availableFacilities"]}
    resuscitation = detail["resuscitationRoom"]
    if detail["statusMessages"] or detail["publicStatusMessages"]:
        logger.warning("진료불가 메시지의 원소 구조를 확인하지 못해 메시지를 담지 않는다 hospital_id=%s", detail["id"])
    longitude, latitude = detail["coordinates"]
    categories = {HospitalCategory(room["type"])}
    if detail["id"] in trauma_center_ids:
        categories.add(HospitalCategory.REGIONAL_TRAUMA_CENTER)
    return Hospital(
        hospital_id=detail["id"],
        name=detail["name"],
        longitude=longitude,
        latitude=latitude,
        distance_km=room["distance"],
        categories=frozenset(categories),
        departments=frozenset(detail["specialty"]),
        er_beds=beds.get(_ER_BED_KEY, _NO_BEDS),
        icu_beds={t: beds.get(key, _NO_BEDS) for t, key in _ICU_BED_KEYS.items()},
        operating_room_beds=beds.get(_OPERATING_ROOM_KEY, _NO_BEDS),
        ward_beds=beds.get(_WARD_KEY, _NO_BEDS),
        resuscitation_room=(
            BedCount(available=resuscitation["availableCount"], total=resuscitation["totalCount"])
            if resuscitation
            else _NO_BEDS
        ),
        beds_updated_at=(
            datetime.strptime(detail["lastUpdatedAt"], "%Y-%m-%d %H:%M:%S") if detail["lastUpdatedAt"] else None
        ),
        congestion=room["congestion"],
        congestion_status=CongestionStatus(room["status"]),
        disease_acceptance={
            a["key"]: DiseaseAcceptance(status=AcceptanceStatus(a["value"]), restriction=a["message"])
            for a in detail["acceptanceCapabilities"]
        },
        equipment={t: equipment.get(key) for t, key in _EQUIPMENT_KEYS.items()},
        delivery_room=facilities.get(_DELIVERY_ROOM_KEY),
        block_messages=(),
    )
