"""EtaProvider의 Tmap ETA API 구현. ETA 계산(F)이 쓴다.

- Tmap 자동차 경로안내(POST /tmap/routes?version=1)를 병원마다 한 번씩 병렬로 호출하고, 응답의 경로 요약
  (features[0].properties)에서 총 거리(totalDistance, m)와 총 소요 시간(totalTime, 초)을 읽는다.
- Tmap ETA API는 에어갭 현장에서 예외적으로 호출할 수 있는 외부 API다.
- 앱 키는 config/settings.yaml의 tmap_app_key에서 읽는다. 저장소의 키는 개발용 테스트 키다.
"""

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from aimp.common.settings import settings
from aimp.domain.hospital import Hospital
from aimp.domain.eta import Eta, EtaMethod
from aimp.ports.eta_provider import straight_line_eta

logger = logging.getLogger(__name__)

# 서버 시간대와 관계없이 도착 예정 시각을 한국 시간으로 계산한다.
KST = timezone(timedelta(hours=9))
_SEARCH_OPTION = "0"  # 경로 탐색 옵션. 0은 교통최적+추천(Tmap 기본값)


class TmapEtaProvider:
    """Tmap ETA API로 ETA를 구하는 EtaProvider 구현.

    - 요청마다 timeout(초)을 건다. 재시도하지 않는다.
    - 호출이 실패하거나 응답 형식이 예상과 다르면 그 병원만 직선거리로 대신한다. 다른 병원의 ETA는 그대로 쓴다.
    """

    def __init__(
        self,
        url: str = settings.tmap_eta_url,
        timeout: float = settings.tmap_eta_timeout_seconds,
        app_key: str = settings.tmap_app_key,
    ):
        if not app_key:
            raise ValueError("Tmap 앱 키(tmap_app_key)가 비어 있습니다")
        self._url = url
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"appKey": app_key, "Accept": "application/json"})

    def estimate(self, longitude: float, latitude: float, hospitals: Sequence[Hospital]) -> list[Eta]:
        if not hospitals:
            return []
        with ThreadPoolExecutor(max_workers=len(hospitals)) as pool:
            return list(pool.map(lambda hospital: self._estimate_one(longitude, latitude, hospital), hospitals))

    def _estimate_one(self, longitude: float, latitude: float, hospital: Hospital) -> Eta:
        body = {
            "startX": longitude,
            "startY": latitude,
            "endX": hospital.longitude,
            "endY": hospital.latitude,
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
            "searchOption": _SEARCH_OPTION,
        }
        try:
            resp = self._session.post(self._url, params={"version": 1}, json=body, timeout=self._timeout)
            resp.raise_for_status()
            summary = resp.json()["features"][0]["properties"]
            distance_m = int(summary["totalDistance"])
            travel_seconds = int(summary["totalTime"])
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
            logger.warning("Tmap ETA API 호출 실패, 직선거리로 대신한다 hospital_id=%s error=%r", hospital.hospital_id, e)
            return straight_line_eta(hospital)
        return Eta(
            hospital_id=hospital.hospital_id,
            method=EtaMethod.TMAP,
            distance_km=distance_m / 1000,
            travel_seconds=travel_seconds,
            arrival_at=datetime.now(KST) + timedelta(seconds=travel_seconds),
        )
