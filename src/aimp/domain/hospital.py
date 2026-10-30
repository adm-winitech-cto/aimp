"""병원 데이터. 병원 데이터 조회(C0)의 출력.

클래스 docstring의 'API' 항목은 병원정보 검색 API(docs/10_설계/interface_hospital_api.md)에서 값을 가져올 필드다.
API가 주지 않는 병상 종류(소아 응급실, 외상소생실, 내과 중환자실 등)는 담지 않는다. 제공처가 이 값을 제공할 수 없다고 답했다.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from aimp.domain.types import HospitalCategory


class IcuBedType(StrEnum):
    """중환자실 병상 종류.

    API: 병원 상세 availableBeds[]의 key
        GENERAL: hvicc
        NEUROLOGY: hvcc
        THORACIC_SURGERY: hvccc
        NEONATAL: hvncc
    """

    GENERAL = "일반"
    NEUROLOGY = "신경과"
    THORACIC_SURGERY = "흉부외과"
    NEONATAL = "신생아"


class Equipment(StrEnum):
    """장비.

    API: 병원 상세 availableEquipment[]의 key
        CT: hvctayn
        MRI: hvmriayn
        ANGIOGRAPHY: hvangioayn
        VENTILATOR: hvventiayn
        PREMATURE_VENTILATOR: hvventisoayn
        INCUBATOR: hvincuayn
        CRRT: hvcrrtayn
        ECMO: hvecmoayn
        HYPERBARIC_OXYGEN: hvoxyayn
        HYPOTHERMIA: hvhypoayn
        AMBULANCE: hvamyn
    """

    CT = "CT"
    MRI = "MRI"
    ANGIOGRAPHY = "혈관촬영기"
    VENTILATOR = "인공호흡기"
    PREMATURE_VENTILATOR = "인공호흡기(조산아)"
    INCUBATOR = "인큐베이터"
    CRRT = "CRRT"
    ECMO = "ECMO"
    HYPERBARIC_OXYGEN = "고압산소치료기"
    HYPOTHERMIA = "저체온치료기"
    AMBULANCE = "구급차"


class AcceptanceStatus(StrEnum):
    """중증질환 수용가능 여부. API: 병원 상세 acceptanceCapabilities[].value"""

    AVAILABLE = "Y"
    UNAVAILABLE = "불가능"
    NOT_PROVIDED = "정보미제공"


class CongestionStatus(StrEnum):
    """응급실 혼잡 상태. API: 응급실 목록 items[].status"""

    RELAXED = "여유있음"
    NORMAL = "보통"
    CROWDED = "혼잡"
    NO_DATA = "정보없음"


@dataclass(frozen=True)
class BedCount:
    """병상 종류 하나의 병상 수. API가 값을 주지 않으면 None이다. None은 0(가용병상 없음)과 뜻이 다르다.

    API: 병원 상세 availableBeds[]의 availableCount, totalCount
    """

    available: int | None  # 가용 병상 수
    # 전체 병상 수로 보이지만 available보다 작은 병원이 있어 뜻을 제공처에 확인해야 한다.
    total: int | None


@dataclass(frozen=True)
class DiseaseAcceptance:
    """중증질환 하나의 수용가능 여부. API: 병원 상세 acceptanceCapabilities[]의 원소 하나"""

    status: AcceptanceStatus  # API: value
    # 병원이 받을 수 있는 연령·체중 제한(예: "1500g 이상가능"). 영유아·저체중출생아 항목에만 온다. API: message
    restriction: str | None


# 병상 dict 필드가 있어서 frozen으로 두지 않는다. frozen이면 해시할 수 있는 것처럼 보이지만 해시하면 오류가 난다.
@dataclass
class Hospital:
    """조회 시점에 응급실을 운영 중인 병원 한 곳.

    icu_beds와 equipment는 모든 종류를 키로 담는다. API가 그 종류의 값을 주지 않으면 BedCount의 두 값이나
    equipment의 값이 None이다. 환자에게 어떤 병상 종류를 셀지는 후보 필터가 정한다.

    API
        hospital_id: id. 응급의료기관 기관ID(hpid)와 같은 값
        name: name
        longitude, latitude: coordinates ([경도, 위도])
        distance_km: 응급실 목록 items[].distance. 요청의 환자 위치에서 병원까지의 직선거리
        categories: 응급실 목록 items[].type (권역응급의료센터, 지역응급의료센터, 지역응급의료기관).
            API에 권역외상센터 분류가 없어서, 권역외상센터는 config/trauma_centers.yaml의 hpid 목록으로 정한다
        departments: 병원 상세 specialty. 값은 /specialties의 진료과목 명칭
        er_beds: 병원 상세 availableBeds[]의 hvec
        icu_beds: 병원 상세 availableBeds[]. 종류별 key는 IcuBedType 참고
        operating_room_beds: 병원 상세 availableBeds[]의 hvoc
        ward_beds: 병원 상세 availableBeds[]의 hvgc
        resuscitation_room: 병원 상세 resuscitationRoom. 어느 병상의 수인지 제공처에 확인해야 한다
        beds_updated_at: 병원 상세 lastUpdatedAt (yyyy-MM-dd HH:mm:ss)
        congestion, congestion_status: 응급실 목록 items[].congestion, items[].status
        disease_acceptance: 병원 상세 acceptanceCapabilities[]. 키는 key(mkioskty1~mkioskty28)
        equipment: 병원 상세 availableEquipment[]의 available. value가 Y면 True, N이나 N1이면 False다.
            종류별 key는 Equipment 참고
        delivery_room: 병원 상세 availableFacilities[]의 hv42(분만실)의 available
        block_messages: 병원 상세 statusMessages, publicStatusMessages의 message. 병원이 쓴 자유 문장이라서 진료과를
            필드로 읽을 수 없다. 중증 메시지는 문장 앞에 중증질환 이름을 붙인다(예: "산부인과 응급(분만): 일시적 불가").
            API는 차단 종료 시각(endDateTime)이 지난 메시지도 주므로, 조회 시각이 차단 시작 시각(startDateTime)과
            종료 시각 사이에 있는 메시지만 담는다
    """

    hospital_id: str
    name: str
    longitude: float  # WGS84
    latitude: float  # WGS84
    distance_km: float  # 환자 위치에서의 직선거리. API가 소수 첫째 자리까지 준다
    categories: frozenset[HospitalCategory]  # 병원이 속한 분류. 하나 이상
    departments: frozenset[str]  # 보유 진료과
    er_beds: BedCount  # 응급실 가용병상
    icu_beds: dict[IcuBedType, BedCount]  # 중환자실 가용병상
    operating_room_beds: BedCount  # 수술실 가용병상
    ward_beds: BedCount  # 입원실 가용병상
    resuscitation_room: BedCount  # 소생실 병상
    beds_updated_at: datetime | None  # 병상 데이터 갱신 시각. 신선도 판정에 쓴다.
    congestion: int | None  # 응급실 혼잡도 (0~100)
    congestion_status: CongestionStatus
    disease_acceptance: dict[str, DiseaseAcceptance]  # 중증질환 코드별 수용가능 여부
    equipment: dict[Equipment, bool | None]  # 장비 가용 여부
    delivery_room: bool | None  # 분만실 가용 여부
    block_messages: tuple[str, ...]  # 진료불가 메시지 문장. 두 필드에 같은 문장이 있으면 한 번만 담는다
