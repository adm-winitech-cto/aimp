"""병원 데이터. 병원 데이터 조회(C0)의 출력.

클래스 docstring의 'DB' 항목은 docs/erd_hospital.mmd 기준으로 값을 가져올 테이블과 컬럼이다.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class HospitalCategory(StrEnum):
    """병원 분류. 병원 조회 조건과 규칙 엔진의 병원 등급 조건에 쓴다.

    권역외상센터는 응급의료기관 등급과 따로 지정되므로, 한 병원이 권역외상센터이면서 권역응급의료센터일 수 있다.
    """

    REGIONAL_TRAUMA_CENTER = "권역외상센터"
    REGIONAL_EMERGENCY_CENTER = "권역응급의료센터"
    LOCAL_EMERGENCY_CENTER = "지역응급의료센터"
    LOCAL_EMERGENCY_INSTITUTION = "지역응급의료기관"
    OTHER = "기타"  # 위 분류에 속하지 않는 응급실 운영 기관


class ErBedType(StrEnum):
    """응급실 병상 종류.

    DB: tapi_emrm_rltm_avl_sckbd_info_inq(응급실시간가용병상정보조회)의 컬럼
        GENERAL: hvec
        PEDIATRIC: hv28
        TRAUMA_RESUSCITATION: hv60
        TRAUMA_CARE_AREA: hv61
        NEGATIVE_PRESSURE_ISOLATION: hv29 (응급실 음압 격리 병상)
        ISOLATION: hv30 (응급실 일반 격리 병상)
        ISOLATION_AREA_NEGATIVE_PRESSURE: hv13
        ISOLATION_AREA_GENERAL: hv14
        PEDIATRIC_NEGATIVE_PRESSURE_ISOLATION: hv15
        PEDIATRIC_ISOLATION: hv16
        COHORT_ISOLATION: hv27
    """

    GENERAL = "일반"
    PEDIATRIC = "소아"
    TRAUMA_RESUSCITATION = "외상소생실"
    TRAUMA_CARE_AREA = "외상환자진료구역"
    NEGATIVE_PRESSURE_ISOLATION = "음압격리"
    ISOLATION = "일반격리"
    ISOLATION_AREA_NEGATIVE_PRESSURE = "격리진료구역 음압격리"
    ISOLATION_AREA_GENERAL = "격리진료구역 일반격리"
    PEDIATRIC_NEGATIVE_PRESSURE_ISOLATION = "소아 음압격리"
    PEDIATRIC_ISOLATION = "소아 일반격리"
    COHORT_ISOLATION = "코호트 격리"


class IcuBedType(StrEnum):
    """중환자실 병상 종류.

    DB: tapi_emrm_rltm_avl_sckbd_info_inq(응급실시간가용병상정보조회)의 컬럼
        GENERAL: hvicc
        INTERNAL_MEDICINE: hv2
        SURGERY: hv3
        NEUROLOGY: hvcc
        NEUROSURGERY: hv6
        THORACIC_SURGERY: hvccc
        CARDIOLOGY: hv34
        TRAUMA: hv9
        BURN: hv8
        PEDIATRIC: hv32
        NEONATAL: hvncc
        EMERGENCY: hv31
        EMERGENCY_PEDIATRIC: hv33
        NEGATIVE_PRESSURE_ISOLATION: hv35
        EMERGENCY_NEGATIVE_PRESSURE_ISOLATION: hv17
        EMERGENCY_ISOLATION: hv18
        INFECTIOUS_DISEASE: hv22
        INFECTIOUS_DISEASE_NEGATIVE_PRESSURE: hv23
        INFECTION_SEVERE: hv24
    """

    GENERAL = "일반"
    INTERNAL_MEDICINE = "내과"
    SURGERY = "외과"
    NEUROLOGY = "신경과"
    NEUROSURGERY = "신경외과"
    THORACIC_SURGERY = "흉부외과"
    CARDIOLOGY = "심장내과"
    TRAUMA = "외상"
    BURN = "화상"
    PEDIATRIC = "소아"
    NEONATAL = "신생아"
    EMERGENCY = "응급전용"
    EMERGENCY_PEDIATRIC = "응급전용 소아"
    NEGATIVE_PRESSURE_ISOLATION = "음압격리"
    EMERGENCY_NEGATIVE_PRESSURE_ISOLATION = "응급전용 음압격리"
    EMERGENCY_ISOLATION = "응급전용 일반격리"
    INFECTIOUS_DISEASE = "감염병 전담"
    INFECTIOUS_DISEASE_NEGATIVE_PRESSURE = "감염병 전담 음압격리"
    INFECTION_SEVERE = "감염 중증"


@dataclass(frozen=True)
class BlockMessage:
    """병원이 공개한 진료불가 메시지. 조회 시점에 유효한 메시지만 담는다.

    DB: tapi_emrm_nd_svredss_msg_inq(응급실및중증질환메시지조회)의 한 행
        disease_code: symtypcod (중증질환구분). 응급실 메시지와 중증질환 메시지는 symblkmsgtyp(메시지구분)로
            나뉘는 것으로 보이며 확인이 필요하다.
        text: symblkmsg (전달메시지)
        조회 조건: 차단시작(symblksttdtm)과 차단종료(symblkenddtm) 사이에 조회 시점이 들어가는 행
    """

    disease_code: str | None  # 특정 중증질환에 대한 메시지면 질환 코드, 응급실 전체에 대한 메시지면 None
    text: str


# 병상 dict 필드가 있어서 frozen으로 두지 않는다. frozen이면 해시할 수 있는 것처럼 보이지만 해시하면 오류가 난다.
@dataclass
class Hospital:
    """조회 시점에 응급실을 운영 중인 병원 한 곳.

    er_beds와 icu_beds는 모든 병상 종류를 키로 담는다. 병원이 그 종류의 값을 제공하지 않으면 값은 None이다.
    환자에게 어떤 병상 종류를 셀지는 후보 필터가 정한다.

    DB
        hospital_id: tapi_emgc_mdlcnst_list_info_inq.hpid (응급의료기관목록정보조회 기관ID).
            다른 tapi_* 테이블도 hpid로 결합한다.
        name: tapi_emgc_mdlcnst_list_info_inq.dutyname (기관명1)
        longitude, latitude: tapi_emgc_mdlcnst_list_info_inq.wgs84lon, wgs84lat (병원경도, 병원위도).
            문자열 컬럼이라 숫자로 변환한다.
        categories: 응급의료기관 등급은 tapi_emgc_mdlcnst_list_info_inq.dutyemcls (응급의료기관분류 코드),
            권역외상센터는 tapi_trmacntr_pstn_info_inq.dutylvkl (외상센터위치정보조회 외상센터등급).
            코드를 HospitalCategory로 바꿔 담는다. 각 분류를 뜻하는 코드 값은 확인이 필요하다.
        departments: tapi_emgc_mdlcnst_bsc_info_inq.dgididname (응급의료기관기본정보조회 진료과목)
        er_beds, icu_beds: tapi_emrm_rltm_avl_sckbd_info_inq (응급실시간가용병상정보조회).
            종류별 컬럼은 ErBedType, IcuBedType 참고
        beds_updated_at: tapi_emrm_rltm_avl_sckbd_info_inq.hvidate (입력일시, 14자리 문자열)
        accepting_diseases: tapi_svredss_ptn_actc_psblty_info_inq.mkioskty1~mkioskty27 (중증질환환자수용가능정보조회).
            응급의료기관기본정보조회와 외상센터기본정보조회의 같은 이름 컬럼은 뜻이 다르므로 쓰지 않는다.
        block_messages: tapi_emrm_nd_svredss_msg_inq (응급실및중증질환메시지조회). 컬럼은 BlockMessage 참고
        조회 조건: tapi_emgc_mdlcnst_bsc_info_inq.dutyeryn (응급의료기관기본정보조회 응급실운영여부)
    """

    hospital_id: str
    name: str
    longitude: float  # WGS84
    latitude: float  # WGS84
    categories: frozenset[HospitalCategory]  # 병원이 속한 분류. 하나 이상
    departments: frozenset[str]  # 보유 진료과. Pre-KTAS 조회 테이블의 진료과명과 같은 값
    er_beds: dict[ErBedType, int | None]  # 응급실 가용병상
    icu_beds: dict[IcuBedType, int | None]  # 중환자실 가용병상
    beds_updated_at: datetime | None  # 병상 데이터 갱신 시각. 신선도 판정에 쓴다.
    accepting_diseases: frozenset[str]  # 지금 수용 가능한 중증질환 코드
    block_messages: tuple[BlockMessage, ...]
