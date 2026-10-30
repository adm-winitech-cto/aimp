"""요청 스키마의 필드 매핑과 '생략 시 처리' 기본값 테스트."""

from datetime import datetime

from aimp.api.request import RecommendRequest


def test_interface_example_maps_to_fields(example_request):
    """interface.md 예시 요청의 camelCase 필드가 snake_case 속성으로 옮겨지고, 시각 문자열이 datetime으로 바뀌는지 확인한다."""
    req = RecommendRequest.model_validate(example_request)
    patient = req.patient

    assert req.incident_id == "INC-20260831-000123"
    assert req.request_seq == 2
    assert req.requested_at == datetime(2026, 8, 31, 17, 12, 0)
    assert req.recommend_count == 3
    assert patient.info.age == 65
    assert patient.consciousness_level == "명료"
    assert patient.major_severe_type is None
    assert patient.pre_ktas.level == 2
    assert patient.pre_ktas.assessment_detail == "15세 이상 - 근골격계 - 하지 손상 - 개방성 골절 또는 신경혈관 장애"
    assert patient.vital_signs.recorded_at == datetime(2026, 8, 31, 17, 11, 26)
    assert patient.vital_signs.spo2_percent == 97
    assert patient.medical_history[2].detail == "고지혈증"
    assert patient.remark == "자유서술"
    assert (patient.location.longitude, patient.location.latitude) == (128.5911, 35.8714)
    assert req.rejected_hospitals[0].hospital_name == "OO대학교병원"
    assert req.rejected_hospitals[0].rejected_at == datetime(2026, 8, 31, 17, 20, 15)


def test_omitted_optional_keys_use_defaults(example_request, example_patient):
    """optional 키를 생략하면 interface.md '생략 시 처리' 열의 기본값이 들어가는지 확인한다."""
    del example_request["rejectedHospitals"]
    for key in ("consciousnessLevel", "majorSevereType", "vitalSigns", "medicalHistory", "medications", "remark"):
        del example_patient[key]

    req = RecommendRequest.model_validate(example_request)
    patient = req.patient

    assert req.rejected_hospitals == []
    assert patient.consciousness_level is None
    assert patient.major_severe_type is None
    assert patient.vital_signs is None
    assert patient.medical_history == []
    assert patient.medications == []
    assert patient.remark is None


def test_recommend_count_accepts_integer(example_request):
    """추천받을 병원 수에 정수가 오면 그 값이 들어가는지 확인한다."""
    example_request["recommendCount"] = 2

    assert RecommendRequest.model_validate(example_request).recommend_count == 2


def test_age_accepts_fraction(example_request, example_patient):
    """interface.md 타입(number)대로 나이에 소수(예: 생후 6개월 0.5세)를 받는지 확인한다."""
    example_patient["info"]["age"] = 0.5

    assert RecommendRequest.model_validate(example_request).patient.info.age == 0.5


def test_omitted_vital_sign_values_are_null(example_request, example_patient):
    """활력징후에서 recordedAt 외의 키를 생략하면 각 값이 None이 되는지 확인한다."""
    example_patient["vitalSigns"] = {"recordedAt": "2026-08-31 17:11:26"}

    vital = RecommendRequest.model_validate(example_request).patient.vital_signs

    assert vital.measured_at is None
    assert vital.systolic_bp_mm_hg is None
    assert vital.diastolic_bp_mm_hg is None
    assert vital.pulse_per_min is None
    assert vital.respiratory_rate_per_min is None
    assert vital.body_temp_celsius is None
    assert vital.spo2_percent is None
    assert vital.blood_glucose_mg_dl is None


def test_omitted_medical_history_detail_is_null(example_request, example_patient):
    """과거력 항목에서 detail 키를 생략하면 detail이 None이 되는지 확인한다."""
    example_patient["medicalHistory"] = [{"diseaseName": "당뇨"}]

    assert RecommendRequest.model_validate(example_request).patient.medical_history[0].detail is None


def test_omitted_rejected_hospital_reason_is_null(example_request):
    """거절 병원 항목에서 reason 키를 생략하면 reason이 None이 되는지 확인한다."""
    example_request["rejectedHospitals"] = [{"hospitalName": "OO대학교병원", "rejectedAt": "2026-08-31 17:20:15"}]

    assert RecommendRequest.model_validate(example_request).rejected_hospitals[0].reason is None


def test_null_special_patient_values_mean_not_applicable(example_request):
    """patient.specialInfo의 하위 값이 null이면 '해당 없음'(None)으로 받아들이는지 확인한다."""
    special = RecommendRequest.model_validate(example_request).patient.special_info

    assert special.pregnancy_info is None
    assert special.newborn_info is None


def test_pregnancy_info_object_is_kept(example_request, example_patient):
    """pregnancyInfo에 객체가 오면 구조와 관계없이 받은 그대로 보관하는지 확인한다."""
    # pregnancyInfo의 객체 구조는 미정이라 받은 객체를 그대로 보관한다.
    example_patient["specialInfo"]["pregnancyInfo"] = {"weeks": 32}

    special = RecommendRequest.model_validate(example_request).patient.special_info

    assert special.pregnancy_info == {"weeks": 32}
