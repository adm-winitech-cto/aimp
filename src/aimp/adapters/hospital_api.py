"""HospitalRepository의 병원정보 검색 API 구현. 병원 데이터 조회(C0)가 쓴다.

- 응급실 목록(/emergency-rooms)을 환자 위치에서 반경 안으로 조회해 후보 병원, 직선거리, 혼잡도를 받는다.
- 중증질환 수용가능 여부와 진료과목은 병원 상세(/{id})에만 있으므로, 후보 병원마다 병원 상세를 병렬로 호출한다.
- 인증 키는 환경 변수 HOSPITAL_API_CLIENT_ID, HOSPITAL_API_KEY에서 읽는다. 키를 설정 파일과 저장소에 넣지 않는다.
- API 응답 필드와 Hospital 필드의 대응은 domain/hospital.py의 docstring에 있다.
"""

import logging
import os
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import requests

from aimp.common.settings import settings
from aimp.domain.hospital import (
    AcceptanceStatus,
    BedCount,
    CongestionStatus,
    DiseaseAcceptance,
    Equipment,
    ErBedType,
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

# 병원 상세 availableBeds[]의 key. 여기 없는 병상 종류는 API가 주지 않는다.
_ER_BED_KEYS = {ErBedType.GENERAL: "hvec"}
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
        if HospitalCategory.REGIONAL_TRAUMA_CENTER in categories:
            logger.warning("병원정보 검색 API에 권역외상센터 분류가 없어 권역외상센터를 조회하지 못한다")
        classes = [_EMERGENCY_CLASSES[c] for c in categories if c in _EMERGENCY_CLASSES]
        if not classes:
            return []

        location = {"longitude": longitude, "latitude": latitude}
        rooms = self._emergency_rooms({**location, "radiusKm": self._radius_km, "emergencyClasses": ",".join(classes)})
        with ThreadPoolExecutor(max_workers=self._max_concurrency) as pool:
            details = list(pool.map(lambda room: self._get(f"/{room['id']}", location), rooms))
        try:
            return [_to_hospital(room, detail) for room, detail in zip(rooms, details)]
        except (KeyError, TypeError, ValueError) as e:
            raise HospitalLookupError("병원정보 검색 API 응답 형식이 예상과 다릅니다") from e

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


def _to_hospital(room: dict[str, Any], detail: dict[str, Any]) -> Hospital:
    """응급실 목록의 항목 하나와 그 병원의 병원 상세를 Hospital로 바꾼다."""
    beds = {b["key"]: BedCount(available=b["availableCount"], total=b["totalCount"]) for b in detail["availableBeds"]}
    equipment = {e["key"]: e["available"] for e in detail["availableEquipment"]}
    facilities = {f["key"]: f["available"] for f in detail["availableFacilities"]}
    resuscitation = detail["resuscitationRoom"]
    if detail["statusMessages"] or detail["publicStatusMessages"]:
        logger.warning("진료불가 메시지의 원소 구조를 확인하지 못해 메시지를 담지 않는다 hospital_id=%s", detail["id"])
    longitude, latitude = detail["coordinates"]
    return Hospital(
        hospital_id=detail["id"],
        name=detail["name"],
        longitude=longitude,
        latitude=latitude,
        distance_km=room["distance"],
        categories=frozenset({HospitalCategory(room["type"])}),
        departments=frozenset(detail["specialty"]),
        er_beds={t: beds.get(_ER_BED_KEYS.get(t), _NO_BEDS) for t in ErBedType},
        icu_beds={t: beds.get(_ICU_BED_KEYS.get(t), _NO_BEDS) for t in IcuBedType},
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
