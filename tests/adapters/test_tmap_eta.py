"""Tmap ETA API EtaProvider 구현(TmapEtaProvider) 테스트. PRD_v0.1.md F-10 'ETA 계산'의 완료조건(가짜 Tmap 응답의 ETA 변환,
호출 실패 시 직선거리 대체)을 확인한다.

Tmap 자동차 경로안내(POST /tmap/routes)를 흉내 내는 HTTP 서버를 띄워 확인한다.
응답 본문은 Tmap 경로안내 응답에서 경로 요약(features[0].properties)의 필드 구조를 따왔다.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from aimp.adapters.tmap_eta import KST, TmapEtaProvider
from aimp.domain.hospital import BedCount, CongestionStatus, Hospital
from aimp.ports.eta_provider import EtaMethod

LONGITUDE, LATITUDE = 128.5478, 35.8399
NO_BEDS = BedCount(available=None, total=None)


def _hospital(hospital_id: str, longitude: float, latitude: float = 35.84, distance_km: float = 3.2) -> Hospital:
    return Hospital(
        hospital_id=hospital_id,
        name=hospital_id,
        longitude=longitude,
        latitude=latitude,
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


def _route(total_distance: int, total_time: int) -> dict:
    """경로안내 응답. 경로 요약은 출발 지점(pointType S)인 첫 feature의 properties에만 있다."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [LONGITUDE, LATITUDE]},
                "properties": {
                    "totalDistance": total_distance,
                    "totalTime": total_time,
                    "totalFare": 0,
                    "taxiFare": 5000,
                    "index": 0,
                    "pointIndex": 0,
                    "name": "",
                    "description": "출발",
                    "pointType": "S",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[LONGITUDE, LATITUDE], [128.55, 35.84]]},
                "properties": {"index": 1, "lineIndex": 0, "distance": 100, "time": 20},
            },
        ],
    }


class FakeTmap(ThreadingHTTPServer):
    """테스트마다 도착지 경도(endX)별 응답을 정해 둔다. 받은 요청의 검색 조건, 헤더, 본문을 기록한다.

    routes에 없는 도착지에는 HTTP 400을 돌려준다.
    """

    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.routes: dict[float, tuple[int, str]] = {}  # endX: (HTTP 상태 코드, 응답 본문)
        self.delay = 0.0  # 응답 전에 기다리는 시간(초)
        self.requests: list[tuple[dict[str, str], dict[str, str], dict]] = []
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/tmap/routes"

    def respond(self, end_x: float, body: dict | str, status: int = 200) -> None:
        self.routes[end_x] = (status, body if isinstance(body, str) else json.dumps(body))


class _Handler(BaseHTTPRequestHandler):
    server: FakeTmap

    def do_POST(self):
        url = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(url.query).items()}
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with self.server._lock:
            self.server.requests.append((params, dict(self.headers), body))
        time.sleep(self.server.delay)
        status, text = self.server.routes.get(body["endX"], (400, '{"error": {"code": "1100"}}'))
        data = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def tmap():
    server = FakeTmap()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _provider(url: str, timeout: float = 3.0) -> TmapEtaProvider:
    return TmapEtaProvider(url=url, timeout=timeout, app_key="key")


def test_converts_route_summary_to_eta(tmap):
    """경로 요약의 총 거리(m)와 총 소요 시간(초)을 km와 도착 예정 시각(KST)으로 바꾸는지 확인한다."""
    tmap.respond(128.5833, _route(total_distance=3568, total_time=676))

    before = datetime.now(KST)
    [eta] = _provider(tmap.url).estimate(LONGITUDE, LATITUDE, [_hospital("A1", 128.5833)])
    after = datetime.now(KST)

    assert eta.hospital_id == "A1"
    assert eta.method == EtaMethod.TMAP
    assert eta.distance_km == 3.568
    assert eta.travel_seconds == 676
    assert eta.arrival_at.utcoffset() == timedelta(hours=9)
    assert before + timedelta(seconds=676) <= eta.arrival_at <= after + timedelta(seconds=676)


def test_request_uses_location_hospital_and_app_key(tmap):
    """환자 위치를 출발지, 병원 좌표를 도착지로 WGS84 좌표계로 보내고, 앱 키를 헤더에 넣는지 확인한다."""
    tmap.respond(128.5833, _route(3568, 676))

    _provider(tmap.url).estimate(LONGITUDE, LATITUDE, [_hospital("A1", 128.5833, latitude=35.8408)])

    [(params, headers, body)] = tmap.requests
    assert params == {"version": "1"}
    assert headers["appKey"] == "key"
    assert body == {
        "startX": LONGITUDE,
        "startY": LATITUDE,
        "endX": 128.5833,
        "endY": 35.8408,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
    }


def test_calls_once_per_hospital_and_keeps_order(tmap):
    """병원마다 한 번씩 호출하고, 결과를 입력한 병원 순서대로 반환하는지 확인한다."""
    tmap.respond(128.1, _route(1000, 100))
    tmap.respond(128.2, _route(2000, 200))
    tmap.respond(128.3, _route(3000, 300))
    hospitals = [_hospital("C", 128.3), _hospital("A", 128.1), _hospital("B", 128.2)]

    etas = _provider(tmap.url).estimate(LONGITUDE, LATITUDE, hospitals)

    assert [(eta.hospital_id, eta.travel_seconds) for eta in etas] == [("C", 300), ("A", 100), ("B", 200)]
    assert len(tmap.requests) == 3


def test_empty_hospitals_returns_empty_without_call(tmap):
    assert _provider(tmap.url).estimate(LONGITUDE, LATITUDE, []) == []
    assert tmap.requests == []


def _http_error(tmap):
    tmap.respond(128.5833, {"error": {"id": "400", "category": "tmap", "code": "3102", "message": "error"}}, status=400)


def _server_error(tmap):
    tmap.respond(128.5833, "Internal Server Error", status=500)


def _not_json(tmap):
    tmap.respond(128.5833, "<html></html>")


def _missing_summary(tmap):
    tmap.respond(128.5833, {"type": "FeatureCollection", "features": []})


def _timeout(tmap):
    tmap.respond(128.5833, _route(3568, 676))
    tmap.delay = 0.5


@pytest.mark.parametrize("fail", [_http_error, _server_error, _not_json, _missing_summary, _timeout])
def test_failure_falls_back_to_straight_line(tmap, fail):
    """호출이 실패하거나 응답 형식이 예상과 다르면, 병원정보 검색 API가 준 직선거리로 대신하는지 확인한다."""
    fail(tmap)

    [eta] = _provider(tmap.url, timeout=0.1).estimate(
        LONGITUDE, LATITUDE, [_hospital("A1", 128.5833, distance_km=4.2)]
    )

    assert eta.method == EtaMethod.STRAIGHT_LINE
    assert eta.distance_km == 4.2
    assert eta.travel_seconds is None
    assert eta.arrival_at is None


def test_connection_failure_falls_back_to_straight_line(tmap):
    url = tmap.url
    tmap.shutdown()
    tmap.server_close()

    [eta] = _provider(url).estimate(LONGITUDE, LATITUDE, [_hospital("A1", 128.5833, distance_km=4.2)])

    assert eta.method == EtaMethod.STRAIGHT_LINE
    assert eta.distance_km == 4.2


def test_failure_of_one_hospital_keeps_others(tmap):
    """한 병원의 호출만 실패하면 그 병원만 직선거리로 대신하는지 확인한다."""
    tmap.respond(128.1, _route(1000, 100))
    tmap.respond(128.2, "Internal Server Error", status=500)

    etas = _provider(tmap.url).estimate(
        LONGITUDE, LATITUDE, [_hospital("A", 128.1), _hospital("B", 128.2, distance_km=7.5)]
    )

    assert [(eta.hospital_id, eta.method, eta.distance_km) for eta in etas] == [
        ("A", EtaMethod.TMAP, 1.0),
        ("B", EtaMethod.STRAIGHT_LINE, 7.5),
    ]


def test_empty_app_key_raises_value_error():
    with pytest.raises(ValueError, match="tmap_app_key"):
        TmapEtaProvider(url="http://127.0.0.1:1/tmap/routes", app_key="")
