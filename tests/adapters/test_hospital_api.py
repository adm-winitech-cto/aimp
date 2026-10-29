"""병원정보 검색 API HospitalRepository 구현(HospitalApiRepository) 테스트.

응급실 목록(/emergency-rooms)과 병원 상세(/{id})를 흉내 내는 HTTP 서버를 띄워 확인한다.
응답 본문은 2026-10-29 개발서버 응답에서 필드 구조를 따왔다(docs/10_설계/interface_hospital_api.md).
"""

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from aimp.adapters.hospital_api import TRAUMA_CENTER_IDS, HospitalApiRepository, load_trauma_center_ids
from aimp.common.settings import CONFIG_DIR
from aimp.domain.hospital import (
    AcceptanceStatus,
    BedCount,
    CongestionStatus,
    DiseaseAcceptance,
    Equipment,
    IcuBedType,
)
from aimp.domain.types import HospitalCategory
from aimp.ports.hospital_repository import HospitalLookupError

LONGITUDE, LATITUDE = 128.5911, 35.8714
ALL_EMERGENCY = [
    HospitalCategory.REGIONAL_EMERGENCY_CENTER,
    HospitalCategory.LOCAL_EMERGENCY_CENTER,
    HospitalCategory.LOCAL_EMERGENCY_INSTITUTION,
]


def _item(key, value="", available=None, message=None, available_count=None, total_count=None):
    return {
        "key": key,
        "label": key,
        "value": value,
        "available": available,
        "message": message,
        "availableCount": available_count,
        "totalCount": total_count,
    }


def _room(hospital_id: str, distance: float, type_: str = "권역응급의료센터") -> dict:
    """응급실 목록의 항목 하나."""
    return {
        "id": hospital_id,
        "name": f"병원{hospital_id}",
        "type": type_,
        "region": "중구",
        "address": "주소",
        "phone": "053-000-0000",
        "distance": distance,
        "status": "보통",
        "congestion": 75,
        "capacities": [{"label": "응급실", "current": 6, "total": 15}],
        "lastUpdatedAt": "2026-10-01 16:25:00",
        "statusMessage": None,
        "statusMessageDateTime": None,
        "coordinates": [128.6, 35.87],
        "messageCount": 0,
    }


def _detail(hospital_id: str) -> dict:
    """병원 상세. 배열 필드는 값이 다른 경우가 드러나도록 몇 개만 넣었다."""
    return {
        "id": hospital_id,
        "type": "hospital",
        "name": f"병원{hospital_id}",
        "category": "종합병원",
        "emergencyCategory": "권역응급의료센터",
        "district": "중구",
        "address": "주소",
        "phone": "053-000-0000",
        "emergencyPhone": "053-000-0001",
        "distance": 1.2,
        "open": True,
        "hours": "24시간 응급진료",
        "specialty": ["내과", "심장혈관흉부외과"],
        "emergency": True,
        "coordinates": [128.6, 35.87],
        "description": "",
        "postalCode": "",
        "fax": "",
        "mapGuide": "",
        "weeklyHours": [],
        "bedCapacity": [_item("hperyn", "15개")],
        "availableBeds": [
            _item("hvec", "6 / 15", available_count=6, total_count=15),
            _item("hvoc", "10 / 8", available_count=10, total_count=8),
            _item("hvcc", "- / -"),
            _item("hvncc", "0 / 3", available_count=0, total_count=3),
            _item("hvccc", "- / -"),
            _item("hvicc", "17 / 24", available_count=17, total_count=24),
            _item("hvgc", "152 / 451", available_count=152, total_count=451),
        ],
        "availableFacilities": [_item("hv42", "Y", available=True)],
        "resuscitationRoom": {"availableCount": 1, "totalCount": 3},
        "availableEquipment": [
            _item("hvctayn", "Y", available=True),
            _item("hvmriayn", "N1", available=False),
            _item("hvecmoayn", "N", available=False),
        ],
        "acceptanceCapabilities": [
            _item("mkioskty1", "Y", available=True),
            _item("mkioskty2", "불가능", available=False),
            _item("mkioskty15", "정보미제공", message="1500g 이상가능"),
            _item("mkioskty28", "Y", available=True),
        ],
        "lastUpdatedAt": "2026-10-01 16:25:00",
        "statusMessages": [],
        "publicStatusMessages": [],
    }


class FakeHospitalApi(ThreadingHTTPServer):
    """테스트마다 응급실 목록과 병원 상세를 정해 둔다. 받은 요청의 경로, 검색 조건, 헤더를 기록한다.

    반경(radiusKm) 없는 응급실 목록 요청에는 national_rooms(전국 응급실)를 돌려준다.
    """

    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.rooms = [_room("A1", 1.2)]
        self.national_rooms: list[dict] = []
        self.details = {"A1": _detail("A1")}
        self.page_size = 100  # 응급실 목록 한 페이지에 담는 항목 수
        self.status = 200
        self.result = "SUCCESS"
        self.requests: list[tuple[str, dict[str, str], dict[str, str]]] = []
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def paths(self) -> list[str]:
        return [path for path, _, _ in self.requests]


class _Handler(BaseHTTPRequestHandler):
    server: FakeHospitalApi

    def do_GET(self):
        url = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        with self.server._lock:
            self.server.requests.append((url.path, params, dict(self.headers)))
        if url.path == "/emergency-rooms":
            rooms = self.server.rooms if "radiusKm" in params else self.server.national_rooms
            page = int(params["page"])
            size = self.server.page_size
            data = {
                "items": rooms[(page - 1) * size : page * size],
                "totalCount": len(rooms),
                "page": page,
                "pageSize": size,
            }
        else:
            data = self.server.details[url.path.removeprefix("/")]
        body = json.dumps({"result": self.server.result, "data": data}).encode()
        self.send_response(self.server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", "req-1")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def api():
    server = FakeHospitalApi()
    # serve_forever 기본 폴링 간격(0.5초)이면 shutdown()이 테스트마다 최대 0.5초를 기다린다.
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _repository(api: FakeHospitalApi, trauma_center_ids: frozenset[str] = frozenset()) -> HospitalApiRepository:
    return HospitalApiRepository(
        url=api.url,
        timeout=3.0,
        max_concurrency=4,
        radius_km=50.0,
        trauma_center_ids=trauma_center_ids,
        client_id="client",
        api_key="key",
    )


def test_maps_room_and_detail_to_hospital(api):
    """응급실 목록의 항목과 병원 상세를 Hospital 필드로 바꾸는지 확인한다."""
    [hospital] = _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    assert hospital.hospital_id == "A1"
    assert hospital.name == "병원A1"
    assert (hospital.longitude, hospital.latitude) == (128.6, 35.87)
    assert hospital.distance_km == 1.2
    assert hospital.categories == {HospitalCategory.REGIONAL_EMERGENCY_CENTER}
    assert hospital.departments == {"내과", "심장혈관흉부외과"}
    assert hospital.beds_updated_at == datetime(2026, 10, 1, 16, 25)
    assert hospital.congestion == 75
    assert hospital.congestion_status == CongestionStatus.NORMAL
    assert hospital.block_messages == ()


def test_maps_beds(api):
    """병상 종류마다 가용 수와 전체 수를 담고, API 값이 "- / -"이면 두 값을 None으로 두는지 확인한다."""
    [hospital] = _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    assert hospital.er_beds == BedCount(available=6, total=15)
    assert hospital.icu_beds == {
        IcuBedType.GENERAL: BedCount(available=17, total=24),
        IcuBedType.NEUROLOGY: BedCount(available=None, total=None),
        IcuBedType.THORACIC_SURGERY: BedCount(available=None, total=None),
        IcuBedType.NEONATAL: BedCount(available=0, total=3),
    }
    assert hospital.operating_room_beds == BedCount(available=10, total=8)
    assert hospital.ward_beds == BedCount(available=152, total=451)
    assert hospital.resuscitation_room == BedCount(available=1, total=3)


def test_maps_acceptance_equipment_and_facilities(api):
    """중증질환 수용가능 여부의 세 값과 연령·체중 제한, 장비와 분만실의 가용 여부를 담는지 확인한다."""
    [hospital] = _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    assert hospital.disease_acceptance == {
        "mkioskty1": DiseaseAcceptance(status=AcceptanceStatus.AVAILABLE, restriction=None),
        "mkioskty2": DiseaseAcceptance(status=AcceptanceStatus.UNAVAILABLE, restriction=None),
        "mkioskty15": DiseaseAcceptance(status=AcceptanceStatus.NOT_PROVIDED, restriction="1500g 이상가능"),
        "mkioskty28": DiseaseAcceptance(status=AcceptanceStatus.AVAILABLE, restriction=None),
    }
    assert hospital.equipment[Equipment.CT] is True
    assert hospital.equipment[Equipment.MRI] is False  # value N1
    assert hospital.equipment[Equipment.ECMO] is False  # value N
    assert hospital.equipment[Equipment.CRRT] is None  # API 응답에 없는 장비
    assert set(hospital.equipment) == set(Equipment)
    assert hospital.delivery_room is True


def test_missing_resuscitation_room_and_update_time_are_none(api):
    """병원 상세의 resuscitationRoom과 lastUpdatedAt이 null이면 값을 None으로 두는지 확인한다."""
    api.details["A1"]["resuscitationRoom"] = None
    api.details["A1"]["lastUpdatedAt"] = None

    [hospital] = _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    assert hospital.resuscitation_room == BedCount(available=None, total=None)
    assert hospital.beds_updated_at is None


def test_block_messages_keep_sentences_from_both_fields(api):
    """두 메시지 필드의 문장을 순서대로 담고, 빈 문장은 빼고, 같은 문장은 한 번만 담는지 확인한다."""
    api.details["A1"]["statusMessages"] = ["정형외과 수술 불가 (전문의 부재)", "  "]
    api.details["A1"]["publicStatusMessages"] = ["CT 장비 점검 중", "정형외과 수술 불가 (전문의 부재)"]

    [hospital] = _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    assert hospital.block_messages == ("정형외과 수술 불가 (전문의 부재)", "CT 장비 점검 중")


def test_request_uses_location_radius_classes_and_auth_headers(api):
    """응급실 목록은 환자 위치·반경·등급으로, 병원 상세는 환자 위치로 인증 헤더와 함께 조회하는지 확인한다."""
    _repository(api).find_by_categories(
        LONGITUDE,
        LATITUDE,
        [HospitalCategory.REGIONAL_EMERGENCY_CENTER, HospitalCategory.LOCAL_EMERGENCY_CENTER],
    )

    [(list_path, list_params, headers), (detail_path, detail_params, _)] = api.requests
    assert list_path == "/emergency-rooms"
    assert list_params == {
        "longitude": str(LONGITUDE),
        "latitude": str(LATITUDE),
        "radiusKm": "50.0",
        "emergencyClasses": "REGIONAL_CENTER,LOCAL_CENTER",
        "page": "1",
        "pageSize": "100",
    }
    assert headers["X-GGFI-Client-Id"] == "client"
    assert headers["X-GGFI-API-Key"] == "key"
    assert detail_path == "/A1"
    assert detail_params == {"longitude": str(LONGITUDE), "latitude": str(LATITUDE)}


def test_reads_all_pages_and_keeps_room_order(api):
    """응급실 목록이 여러 페이지면 모든 페이지를 읽고, 병원 순서를 응급실 목록의 순서대로 두는지 확인한다."""
    api.page_size = 2
    api.rooms = [_room(f"A{i}", float(i)) for i in range(1, 6)]
    api.details = {f"A{i}": _detail(f"A{i}") for i in range(1, 6)}

    hospitals = _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    assert [h.hospital_id for h in hospitals] == ["A1", "A2", "A3", "A4", "A5"]
    assert [h.distance_km for h in hospitals] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert [params["page"] for path, params, _ in api.requests if path == "/emergency-rooms"] == ["1", "2", "3"]


def test_trauma_centers_are_picked_from_national_list_by_hpid(api):
    """권역외상센터는 반경과 등급 조건 없이 전국 응급실 목록을 읽어, 설정 파일의 hpid에 있는 병원만 고르는지 확인한다."""
    api.national_rooms = [_room("T1", 80.0), _room("A9", 2.0), _room("T2", 120.0, "지역응급의료센터")]
    api.details.update({hospital_id: _detail(hospital_id) for hospital_id in ["T1", "T2"]})

    hospitals = _repository(api, frozenset({"T1", "T2"})).find_by_categories(
        LONGITUDE, LATITUDE, [HospitalCategory.REGIONAL_TRAUMA_CENTER]
    )

    assert [(h.hospital_id, h.distance_km) for h in hospitals] == [("T1", 80.0), ("T2", 120.0)]
    assert hospitals[1].categories == {
        HospitalCategory.LOCAL_EMERGENCY_CENTER,
        HospitalCategory.REGIONAL_TRAUMA_CENTER,
    }
    [(_, list_params, _)] = [request for request in api.requests if request[0] == "/emergency-rooms"]
    assert list_params == {"longitude": str(LONGITUDE), "latitude": str(LATITUDE), "page": "1", "pageSize": "100"}


def test_trauma_centers_merge_with_grade_query_by_distance(api):
    """권역외상센터와 등급 조건을 함께 찾으면, 두 조회 결과를 중복 없이 합쳐 직선거리 순으로 두는지 확인한다."""
    api.rooms = [_room("A1", 1.2), _room("T1", 30.0)]
    api.national_rooms = [_room("A1", 1.2), _room("T1", 30.0), _room("T2", 5.0)]
    api.details.update({hospital_id: _detail(hospital_id) for hospital_id in ["T1", "T2"]})

    hospitals = _repository(api, frozenset({"T1", "T2"})).find_by_categories(
        LONGITUDE, LATITUDE, [HospitalCategory.REGIONAL_TRAUMA_CENTER, HospitalCategory.REGIONAL_EMERGENCY_CENTER]
    )

    assert [h.hospital_id for h in hospitals] == ["A1", "T2", "T1"]
    assert HospitalCategory.REGIONAL_TRAUMA_CENTER not in hospitals[0].categories
    assert HospitalCategory.REGIONAL_TRAUMA_CENTER in hospitals[2].categories  # 등급 조건으로 찾은 권역외상센터


def test_empty_trauma_center_list_returns_empty_without_call(api):
    """권역외상센터 목록이 비어 있으면, 권역외상센터만 찾을 때 API를 호출하지 않고 빈 목록을 반환하는지 확인한다."""
    assert _repository(api).find_by_categories(LONGITUDE, LATITUDE, [HospitalCategory.REGIONAL_TRAUMA_CENTER]) == []
    assert api.requests == []


def test_trauma_center_file_loads():
    """저장소의 권역외상센터 목록 파일을 읽을 수 있는지 확인한다."""
    assert load_trauma_center_ids(CONFIG_DIR / "trauma_centers.yaml") == TRAUMA_CENTER_IDS


@pytest.mark.parametrize(
    "text",
    ["regional_trauma_centers: [A1, A2]\n", "trauma_centers: {}\n", "regional_trauma_centers: {A1: x, A1: y}\n"],
    ids=["list-not-mapping", "unknown-key", "duplicate-hpid"],
)
def test_malformed_trauma_center_file_fails_to_load(tmp_path, text):
    """권역외상센터 목록 파일의 형식이 틀리거나 같은 hpid가 두 번 나오면 읽지 못하는지 확인한다."""
    path = tmp_path / "trauma_centers.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError):
        load_trauma_center_ids(path)


def test_empty_categories_raises_value_error(api):
    """찾을 병원 분류가 없으면 ValueError를 내는지 확인한다."""
    with pytest.raises(ValueError):
        _repository(api).find_by_categories(LONGITUDE, LATITUDE, [])


def test_server_error_raises_lookup_error_with_request_id(api):
    """API가 오류 응답을 보내면 HospitalLookupError를 내고, 메시지에 X-Request-Id를 담는지 확인한다."""
    api.status = 500

    with pytest.raises(HospitalLookupError, match="request_id=req-1"):
        _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)


def test_fail_result_raises_lookup_error(api):
    """HTTP 200이어도 result가 SUCCESS가 아니면 HospitalLookupError를 내는지 확인한다."""
    api.result = "FAIL"

    with pytest.raises(HospitalLookupError):
        _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)


def _unknown_acceptance_value(api):
    api.details["A1"]["acceptanceCapabilities"][0]["value"] = "가능"


def _missing_detail_field(api):
    del api.details["A1"]["specialty"]


def _unknown_room_type(api):
    api.rooms[0]["type"] = "응급실운영신고기관"


def _non_string_message(api):
    api.details["A1"]["statusMessages"] = [{"messageContent": "정형외과 수술 불가"}]


@pytest.mark.parametrize(
    "mutate", [_unknown_acceptance_value, _missing_detail_field, _unknown_room_type, _non_string_message]
)
def test_unexpected_response_raises_lookup_error(api, mutate):
    """모르는 값이 오거나 필드가 빠지면 일부 병원을 빼지 않고 HospitalLookupError를 내는지 확인한다."""
    api.rooms.append(_room("A2", 2.0))
    api.details["A2"] = _detail("A2")
    mutate(api)

    with pytest.raises(HospitalLookupError):
        _repository(api).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)


def test_unreachable_server_raises_lookup_error():
    """API 서버에 연결할 수 없으면 HospitalLookupError를 내는지 확인한다."""
    server = FakeHospitalApi()
    url = server.url
    server.server_close()  # 포트를 닫아 연결이 거부되게 한다.
    repository = HospitalApiRepository(url=url, client_id="client", api_key="key")

    with pytest.raises(HospitalLookupError):
        repository.find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)


def test_missing_credentials_raise_value_error(monkeypatch):
    """인증 키를 인자로 받지 않았고 환경 변수에도 없으면 ValueError를 내는지 확인한다."""
    monkeypatch.delenv("HOSPITAL_API_CLIENT_ID", raising=False)
    monkeypatch.delenv("HOSPITAL_API_KEY", raising=False)

    with pytest.raises(ValueError, match="HOSPITAL_API_KEY"):
        HospitalApiRepository(url="http://127.0.0.1:1")


def test_credentials_read_from_environment(api, monkeypatch):
    """인증 키를 인자로 받지 않으면 환경 변수에서 읽는지 확인한다."""
    monkeypatch.setenv("HOSPITAL_API_CLIENT_ID", "env-client")
    monkeypatch.setenv("HOSPITAL_API_KEY", "env-key")

    HospitalApiRepository(url=api.url).find_by_categories(LONGITUDE, LATITUDE, ALL_EMERGENCY)

    _, _, headers = api.requests[0]
    assert (headers["X-GGFI-Client-Id"], headers["X-GGFI-API-Key"]) == ("env-client", "env-key")
