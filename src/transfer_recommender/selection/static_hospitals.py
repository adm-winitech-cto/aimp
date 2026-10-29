"""정적 병원 목록. 질환군별로 이송 건수가 많은 병원과, 어느 질환군에도 해당하지 않는 환자에게 쓰는 일반 병원 목록이다.

병원 데이터 조회(C0)를 구현하기 전까지 쓰는 임시 데이터다. 목록은 이송 건수가 많은 순서다.
병원 ID는 응급의료기관 기관ID(hpid)다. hpid가 없는 병원은 병원 ID를 비워 두고, 추천 대상에서 뺀다.
"""

from dataclasses import dataclass
from enum import StrEnum


class DiseaseGroup(StrEnum):
    """6대 중증질환 질환군."""

    CEREBROVASCULAR = "뇌혈관질환"
    CARDIOVASCULAR = "심혈관질환"
    CARDIAC_ARREST = "심정지"
    PREGNANCY_DELIVERY = "임신분만"
    PEDIATRIC = "소아"
    SEVERE_TRAUMA = "중증외상"


@dataclass(frozen=True)
class StaticHospital:
    hospital_id: str
    hospital_name: str
    transfer_count: int  # 이송 건수


def _hospitals(*rows: tuple[str, int, str]) -> tuple[StaticHospital, ...]:
    return tuple(StaticHospital(hospital_id, name, count) for hospital_id, count, name in rows)


HOSPITALS_BY_GROUP: dict[DiseaseGroup, tuple[StaticHospital, ...]] = {
    DiseaseGroup.CEREBROVASCULAR: _hospitals(
        ("A2117994", 10, "학교법인을지학원의정부을지대학교병원"),
        ("A2100030", 6, "차의과학대학교분당차병원"),
        ("A2113246", 6, "의료법인양진의료재단평택성모병원"),
        ("A1100043", 5, "강동경희대학교병원"),
        ("A2100040", 5, "가톨릭대학교의정부성모병원"),
    ),
    DiseaseGroup.CARDIOVASCULAR: _hospitals(
        ("A2100040", 10, "가톨릭대학교의정부성모병원"),
        ("A2117994", 6, "학교법인을지학원의정부을지대학교병원"),
        ("A1100035", 5, "서울특별시서울의료원"),
        ("A2100028", 5, "의료법인백송의료재단굿모닝병원"),
        ("A2100030", 3, "차의과학대학교분당차병원"),
    ),
    DiseaseGroup.CARDIAC_ARREST: _hospitals(
        ("A2100012", 2, "가톨릭대학교성빈센트병원"),
        ("A2100040", 2, "가톨릭대학교의정부성모병원"),
        ("A2100035", 2, "경기도의료원파주병원"),
        ("A2100030", 2, "차의과학대학교분당차병원"),
        ("A2100015", 2, "효산의료재단 안양샘병원"),
    ),
    DiseaseGroup.PREGNANCY_DELIVERY: _hospitals(
        ("A1100048", 1, "노원을지대학교병원"),
        ("A2100012", 1, "가톨릭대학교성빈센트병원"),
        ("A2117994", 1, "학교법인을지학원의정부을지대학교병원"),
        ("", 1, "시온여성병원"),
        ("", 1, "운정와이즈병원"),
    ),
    DiseaseGroup.PEDIATRIC: _hospitals(
        ("A1100009", 20, "재단법인아산사회복지재단서울아산병원"),
        ("A2100040", 13, "가톨릭대학교의정부성모병원"),
        ("A2100003", 11, "고려대학교의과대학부속안산병원"),
        ("A2100030", 11, "차의과학대학교분당차병원"),
        ("A2100002", 10, "아주대학교병원"),
    ),
    DiseaseGroup.SEVERE_TRAUMA: _hospitals(
        ("A2100040", 5, "가톨릭대학교의정부성모병원"),
        ("A2100258", 3, "국군수도병원"),
        ("A2100003", 2, "고려대학교의과대학부속안산병원"),
        ("A2100002", 2, "아주대학교병원"),
        ("A2100038", 2, "인제대학교일산백병원"),
    ),
}

# 6대 중증질환에 해당하지 않는 환자에게 시스템이 무작위로 고르는 병원 목록
GENERAL_HOSPITALS: tuple[StaticHospital, ...] = _hospitals(
    ("A2100040", 281, "가톨릭대학교의정부성모병원"),
    ("A2117994", 238, "학교법인을지학원의정부을지대학교병원"),
    ("A2100030", 153, "차의과학대학교분당차병원"),
    ("A2100055", 139, "부천세종병원"),
    ("A2100052", 117, "가톨릭대학교부천성모병원"),
    ("A2100024", 115, "오산한국병원"),
    ("A2100005", 113, "순천향대학교부속부천병원"),
    ("A2100025", 112, "대진의료재단분당제생병원"),
    ("A2121061", 98, "의료법인덕산의료재단수원덕산병원"),
    ("A2100054", 91, "효산의료재단지샘병원"),
    ("A2100002", 87, "아주대학교병원"),
    ("A2100175", 83, "의료법인토마스의료재단윌스기념병원"),
    ("A2100033", 81, "국민건강보험공단일산병원"),
    ("A2100006", 80, "의료법인인봉의료재단뉴고려병원"),
    ("A2100050", 79, "의료법인대인의료재단다니엘종합병원"),
    ("A2100053", 77, "의료법인우리의료재단김포우리병원"),
    ("A2100046", 77, "한림대학교동탄성심병원"),
    ("A2100003", 75, "고려대학교의과대학부속안산병원"),
    ("A2100155", 74, "참조은병원"),
    ("A2100042", 73, "의료법인명지의료재단명지병원"),
)

# 병원 ID → 병원명. 질환군 목록의 병원 중 병원 ID가 있는 병원만 넣는다. LLM 출력의 병원 ID 값 목록이 된다.
GROUP_HOSPITAL_NAMES: dict[str, str] = {
    hospital.hospital_id: hospital.hospital_name
    for hospitals in HOSPITALS_BY_GROUP.values()
    for hospital in hospitals
    if hospital.hospital_id
}
