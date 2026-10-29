"""여러 처리 단계가 공유하는 열거형."""

from enum import StrEnum


class SevereType(StrEnum):
    """4대 중증 구분."""

    CARDIAC_ARREST = "심정지"
    SEVERE_TRAUMA = "중증외상"
    STROKE = "뇌졸중"
    MYOCARDIAL_INFARCTION = "심근경색"


class PatientCategory(StrEnum):
    """적용 규칙. PRD_v0.1.md F-05 '119 이송지침 규칙 엔진'의 환자 분류."""

    SEVERE_TRAUMA = "중증외상"
    MINOR_TRAUMA = "경증외상"
    SEVERE_NON_TRAUMA = "비외상 중증"
    MINOR_NON_TRAUMA = "비외상 경증"
    CARDIAC_ARREST = "심폐정지"
    STROKE_SUSPECTED = "뇌졸중 의증"
    STROKE_SCREENING_POSITIVE = "뇌졸중 선별검사 양성"


class Level(StrEnum):
    """L0은 지침의 원칙 조건, L1은 의료지도를 받아야 적용할 수 있는 완화 조건."""

    L0 = "L0"
    L1 = "L1"


class Resource(StrEnum):
    """환자에게 필요한 특수 자원. PRD_v0.1.md F-02 '중증·특수 자원 판단'의 판정 규칙 표."""

    STROKE_TREATMENT = "뇌경색 재관류중재술 또는 뇌출혈수술"
    MI_REPERFUSION = "심근경색 재관류중재술"
    PEDIATRIC_EMERGENCY = "소아 응급 진료"
    DELIVERY = "분만"


class HospitalCategory(StrEnum):
    """병원 분류. 규칙 엔진의 병원 등급 조건에 쓴다.

    응급의료기관 등급(`dutyemcls`)과 외상센터 등급(`dutylvkl`)은 서로 다른 데이터라서, 병원 하나가 여러 분류에 속할 수 있다
    (예: 권역응급의료센터이면서 권역외상센터).
    전문응급의료센터는 소아, 화상처럼 특정 환자군만 맡으므로 넣지 않았다.
    """

    REGIONAL_EMERGENCY_CENTER = "권역응급의료센터"
    LOCAL_EMERGENCY_CENTER = "지역응급의료센터"
    LOCAL_EMERGENCY_INSTITUTION = "지역응급의료기관"
    REGIONAL_TRAUMA_CENTER = "권역외상센터"


# Department, SevereDiseaseCode, TraumaCriterion은 환자 상태 판단(A1) LLM 출력 스키마에 들어간다.
# docstring이 JSON 스키마의 description이 되어 프롬프트에 들어가므로, 개발자용 설명은 주석에 적는다.


# 「전문의의 수련 및 자격 인정 등에 관한 규정」 제3조가 정한 전문의 전문과목 26개다(2022-11-22 개정 기준). 순서도 조문을 따른다.
# 값은 병원정보 검색 API `/specialties`의 진료과목 명칭과 같아야 후보 필터가 병원의 진료과목(Hospital.departments)과 비교할 수 있다.
# 그래서 조문과 표기가 다른 두 과는 API 명칭을 쓴다. 조문의 "핵의학"은 "핵의학과", "직업환경의학과"는 "작업환경의학과"다.
# API에는 옛 과목명(산업의학과, 치료방사선과, 해부병리과)도 있지만, 지금 전문과목이 아니므로 넣지 않았다.
class Department(StrEnum):
    """진료과."""

    INTERNAL_MEDICINE = "내과"
    NEUROLOGY = "신경과"
    PSYCHIATRY = "정신건강의학과"
    GENERAL_SURGERY = "외과"
    ORTHOPEDIC_SURGERY = "정형외과"
    NEUROSURGERY = "신경외과"
    CARDIOTHORACIC_SURGERY = "심장혈관흉부외과"
    PLASTIC_SURGERY = "성형외과"
    ANESTHESIOLOGY = "마취통증의학과"
    OBSTETRICS_GYNECOLOGY = "산부인과"
    PEDIATRICS = "소아청소년과"
    OPHTHALMOLOGY = "안과"
    OTOLARYNGOLOGY = "이비인후과"
    DERMATOLOGY = "피부과"
    UROLOGY = "비뇨의학과"
    RADIOLOGY = "영상의학과"
    RADIATION_ONCOLOGY = "방사선종양학과"
    PATHOLOGY = "병리과"
    LABORATORY_MEDICINE = "진단검사의학과"
    TUBERCULOSIS = "결핵과"
    REHABILITATION_MEDICINE = "재활의학과"
    PREVENTIVE_MEDICINE = "예방의학과"
    FAMILY_MEDICINE = "가정의학과"
    EMERGENCY_MEDICINE = "응급의학과"
    NUCLEAR_MEDICINE = "핵의학과"
    OCCUPATIONAL_ENVIRONMENTAL_MEDICINE = "작업환경의학과"


# 중증질환환자수용가능정보조회(tapi_svredss_ptn_actc_psblty_info_inq)의 질환 항목 컬럼명이다.
# mkioskty28(응급실 Emergency gate keeper)은 질환이 아니므로 뺐다.
class SevereDiseaseCode(StrEnum):
    """중증응급질환 코드."""

    MKIOSKTY1 = "mkioskty1"
    MKIOSKTY2 = "mkioskty2"
    MKIOSKTY3 = "mkioskty3"
    MKIOSKTY4 = "mkioskty4"
    MKIOSKTY5 = "mkioskty5"
    MKIOSKTY6 = "mkioskty6"
    MKIOSKTY7 = "mkioskty7"
    MKIOSKTY8 = "mkioskty8"
    MKIOSKTY9 = "mkioskty9"
    MKIOSKTY10 = "mkioskty10"
    MKIOSKTY11 = "mkioskty11"
    MKIOSKTY12 = "mkioskty12"
    MKIOSKTY13 = "mkioskty13"
    MKIOSKTY14 = "mkioskty14"
    MKIOSKTY15 = "mkioskty15"
    MKIOSKTY16 = "mkioskty16"
    MKIOSKTY17 = "mkioskty17"
    MKIOSKTY18 = "mkioskty18"
    MKIOSKTY19 = "mkioskty19"
    MKIOSKTY20 = "mkioskty20"
    MKIOSKTY21 = "mkioskty21"
    MKIOSKTY22 = "mkioskty22"
    MKIOSKTY23 = "mkioskty23"
    MKIOSKTY24 = "mkioskty24"
    MKIOSKTY25 = "mkioskty25"
    MKIOSKTY26 = "mkioskty26"
    MKIOSKTY27 = "mkioskty27"


# 중증응급질환 코드별 이름. 환자 상태 판단 프롬프트가 코드의 뜻을 LLM에게 보여 줄 때 쓴다.
SEVERE_DISEASE_NAMES: dict[SevereDiseaseCode, str] = {
    SevereDiseaseCode.MKIOSKTY1: "[재관류중재술] 심근경색",
    SevereDiseaseCode.MKIOSKTY2: "[재관류중재술] 뇌경색",
    SevereDiseaseCode.MKIOSKTY3: "[뇌출혈수술] 거미막하출혈",
    SevereDiseaseCode.MKIOSKTY4: "[뇌출혈수술] 거미막하출혈 외",
    SevereDiseaseCode.MKIOSKTY5: "[대동맥응급] 흉부",
    SevereDiseaseCode.MKIOSKTY6: "[대동맥응급] 복부",
    SevereDiseaseCode.MKIOSKTY7: "[담낭담관질환] 담낭질환",
    SevereDiseaseCode.MKIOSKTY8: "[담낭담관질환] 담도포함질환",
    SevereDiseaseCode.MKIOSKTY9: "[복부응급수술] 비외상",
    SevereDiseaseCode.MKIOSKTY10: "[장중첩/폐색] 영유아",
    SevereDiseaseCode.MKIOSKTY11: "[응급내시경] 성인 위장관",
    SevereDiseaseCode.MKIOSKTY12: "[응급내시경] 영유아 위장관",
    SevereDiseaseCode.MKIOSKTY13: "[응급내시경] 성인 기관지",
    SevereDiseaseCode.MKIOSKTY14: "[응급내시경] 영유아 기관지",
    SevereDiseaseCode.MKIOSKTY15: "[저체중출생아] 집중치료",
    SevereDiseaseCode.MKIOSKTY16: "[산부인과응급] 분만",
    SevereDiseaseCode.MKIOSKTY17: "[산부인과응급] 산과수술",
    SevereDiseaseCode.MKIOSKTY18: "[산부인과응급] 부인과수술",
    SevereDiseaseCode.MKIOSKTY19: "[중증화상] 전문치료",
    SevereDiseaseCode.MKIOSKTY20: "[사지접합] 수족지접합",
    SevereDiseaseCode.MKIOSKTY21: "[사지접합] 수족지접합 외",
    SevereDiseaseCode.MKIOSKTY22: "[응급투석] HD",
    SevereDiseaseCode.MKIOSKTY23: "[응급투석] CRRT",
    SevereDiseaseCode.MKIOSKTY24: "[정신과적응급] 폐쇄병동입원",
    SevereDiseaseCode.MKIOSKTY25: "[안과적수술] 응급",
    SevereDiseaseCode.MKIOSKTY26: "[영상의학혈관중재] 성인",
    SevereDiseaseCode.MKIOSKTY27: "[영상의학혈관중재] 영유아",
}


# "다발성/중증손상" 지침(docs/90_domain/severe-trauma-criteria.md)의 중증외상 기준 항목 중 환자 상태 판단(A1) LLM이 고르는 항목이다.
# 값은 지침 문구를 따른다. 생리학적 기준은 중증도 판정(A2)이 활력징후와 의식상태로 판정하고,
# 특수상황의 위험한 나이는 나이로 판정하므로 넣지 않았다.
class TraumaCriterion(StrEnum):
    """중증외상 기준 항목."""

    # 신체검사 소견에 따른 기준
    PENETRATING_INJURY = "관통 또는 자상(머리, 목, 가슴, 배, 상완부, 대퇴부)"
    FLAIL_CHEST = "동요가슴(flail chest)"
    PROXIMAL_LONG_BONE_FRACTURES = "두 개 이상의 근위부 긴뼈 골절"
    CRUSHED_DEGLOVED_MANGLED_LIMB = "압궤(crushed), 벗겨진(degloved), 썰린(mangled) 사지"
    AMPUTATION_ABOVE_WRIST_OR_ANKLE = "손목, 발목 상부의 절단"
    PELVIC_FRACTURE = "골반 뼈 골절"
    OPEN_OR_DEPRESSED_SKULL_FRACTURE = "열린 또는 함몰 두개골 골절"
    PARALYSIS = "마비"
    # 손상기전에 따른 기준
    FALL = "추락: 성인 6 m 이상(건물 3층 높이 이상), 소아 3 m 이상(건물 2층 높이 이상)"
    VEHICLE_INTRUSION = "고위험 교통사고: 차체 내부 눌림(찌그러짐) 30 cm 이상"
    VEHICLE_DEFORMITY = "고위험 교통사고: 차체 찌그러짐 45 cm 이상"
    EJECTION = "고위험 교통사고: 자동차에서 이탈(튕겨져 나감)"
    DEATH_IN_SAME_VEHICLE = "고위험 교통사고: 동승자의 사망"
    ROLLOVER = "고위험 교통사고: 차량 전복"
    STRUCK_BY_VEHICLE = "자동차-보행자/개인형 이동장치/자전거 충돌로 나가떨어짐, 치임 또는 시속 30 km 이상의 속도로 충돌함"
    MOTORCYCLE_CRASH = "오토바이 시속 30 km 이상의 속도"
    EXPLOSION = "폭발에 의한 직접적 영향"
    # 의학적 질병상태 및 특수상황 (위험한 나이 제외)
    ANTICOAGULATION_OR_BLEEDING_DISORDER = "항응고 질환, 출혈성 질환"
    BURN_WITH_TRAUMA = "화상과 외상이 동반된 경우"
    DIALYSIS = "투석이 필요한 말기신장(콩팥)질환"
    TIME_SENSITIVE_EXTREMITY_INJURY = "시간 지연에 민감한 사지 손상"
    PREGNANCY_OVER_20_WEEKS = "임신 20주 이상"
    EMS_JUDGMENT = "구급대원의 판단"


# 중증외상 기준 항목의 분류. 신체검사 소견과 손상기전 항목은 중증외상 판정에, 특수상황 항목은 특수상황 판정에 쓴다.
INJURY_FINDINGS: frozenset[TraumaCriterion] = frozenset(
    {
        TraumaCriterion.PENETRATING_INJURY,
        TraumaCriterion.FLAIL_CHEST,
        TraumaCriterion.PROXIMAL_LONG_BONE_FRACTURES,
        TraumaCriterion.CRUSHED_DEGLOVED_MANGLED_LIMB,
        TraumaCriterion.AMPUTATION_ABOVE_WRIST_OR_ANKLE,
        TraumaCriterion.PELVIC_FRACTURE,
        TraumaCriterion.OPEN_OR_DEPRESSED_SKULL_FRACTURE,
        TraumaCriterion.PARALYSIS,
    }
)
INJURY_MECHANISMS: frozenset[TraumaCriterion] = frozenset(
    {
        TraumaCriterion.FALL,
        TraumaCriterion.VEHICLE_INTRUSION,
        TraumaCriterion.VEHICLE_DEFORMITY,
        TraumaCriterion.EJECTION,
        TraumaCriterion.DEATH_IN_SAME_VEHICLE,
        TraumaCriterion.ROLLOVER,
        TraumaCriterion.STRUCK_BY_VEHICLE,
        TraumaCriterion.MOTORCYCLE_CRASH,
        TraumaCriterion.EXPLOSION,
    }
)
SPECIAL_SITUATIONS: frozenset[TraumaCriterion] = frozenset(
    {
        TraumaCriterion.ANTICOAGULATION_OR_BLEEDING_DISORDER,
        TraumaCriterion.BURN_WITH_TRAUMA,
        TraumaCriterion.DIALYSIS,
        TraumaCriterion.TIME_SENSITIVE_EXTREMITY_INJURY,
        TraumaCriterion.PREGNANCY_OVER_20_WEEKS,
        TraumaCriterion.EMS_JUDGMENT,
    }
)


class WarningCode(StrEnum):
    """시스템이 응답에 포함하는 경고."""

    NO_VITAL_SIGNS = "활력징후 없음"
    STALE_BED_DATA = "병상 정보 오래됨"
    REMARK_NOT_APPLIED = "비고 미반영"
    ASSESSMENT_FAILED = "환자 상태 판단 실패"
