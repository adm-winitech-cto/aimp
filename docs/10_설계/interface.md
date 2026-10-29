# 인터페이스

본 문서는 응급환자 이송 병원 추천 시스템의 REST API 인터페이스를 정의합니다.

## Inbound 인터페이스

병원선정서비스는 환자 정보와 환자 위치를 담아 시스템에 병원 추천을 요청합니다.

---

## 병원 추천 요청 (Recommend Request)

**Method:** `POST`

**Endpoint:** `/api/v1/recHosp`

**Content-Type:** `application/json`

**Request Body:**

> 아래 예시의 `//` 주석은 각 필드의 한글명입니다. 실제 요청 본문에는 주석을 넣지 않습니다.

```jsonc
{
    "incidentId": "INC-20260831-000123",      // 사건ID
    "requestSeq": 2,                          // 요청차수
    "requestedAt": "2026-08-31 17:12:00",     // 요청시각
    "recommendCount": 3,                      // 추천병원수
    "patient": {                              // 환자
        "info": {                             // 환자정보
            "age": 65,                        // 나이
            "sex": "남",                      // 성별
            "patientType": "일반환자"         // 환자유형
        },
        "chiefComplaint": "발등 개방성 골절", // 주호소
        "symptoms": [                         // 증상
            "골절",
            "열상"
        ],
        "consciousnessLevel": "명료",         // 의식상태
        "majorSevereType": null,              // 4대중증구분
        "preKtas": {                          // Pre-KTAS
            "assessmentRound": 1,             // 평가차수
            "level": 2,                       // 단계
            "assessmentDetail": "15세 이상 - 근골격계 - 하지 손상 - 개방성 골절 또는 신경혈관 장애"  // 평가내용
        },
        "vitalSigns": {                       // 활력징후
            "measuredAt": null,               // 측정시각
            "recordedAt": "2026-08-31 17:11:26",  // 기록시각
            "systolicBpMmHg": 110,            // 수축기혈압_mmHg
            "diastolicBpMmHg": 90,            // 이완기혈압_mmHg
            "pulsePerMin": 97,                // 맥박_분당횟수
            "respiratoryRatePerMin": 18,      // 호흡수_분당횟수
            "bodyTempCelsius": 36.8,          // 체온_섭씨
            "spo2Percent": 97,                // 산소포화도_퍼센트
            "bloodGlucoseMgDl": 210           // 혈당_mg_dL
        },
        "medicalHistory": [                   // 과거력
            {
                "diseaseName": "뇌혈관질환",  // 질환명
                "detail": null                // 상세내용
            },
            {
                "diseaseName": "당뇨",        // 질환명
                "detail": null                // 상세내용
            },
            {
                "diseaseName": "기타",        // 질환명
                "detail": "고지혈증"          // 상세내용
            }
        ],
        "medications": [],                    // 투여약물
        "specialInfo": {                      // 특수환자정보
            "pregnancyInfo": null,            // 임산부정보
            "newbornInfo": null               // 신생아정보
        },
        "remark": "자유서술",                 // 비고
        "location": {                         // 환자위치
            "longitude": 128.5911,            // 환자X좌표 (경도)
            "latitude": 35.8714               // 환자Y좌표 (위도)
        }
    },
    "rejectedHospitals": [                    // 거절병원
        {
            "hospitalName": "OO대학교병원",   // 병원명
            "reason": "응급실 병상 포화",     // 거절사유
            "rejectedAt": "2026-08-31 17:20:15"  // 거절시각
        }
    ]
}
```

**필수 여부 규칙:**
- 필수(`Y`) 필드
    - 병원선정서비스는 필수 필드의 키를 반드시 보내야 합니다.
    - 필수 필드의 키가 없거나, `null`을 허용하지 않는 필드의 값이 `null`이면, 시스템은 `400 Bad Request`를 반환합니다.
- optional(`N`) 필드
    - 병원선정서비스는 optional 필드의 키를 생략할 수 있습니다.
    - 키가 생략되면 시스템은 '생략 시 처리' 열에 적힌 값으로 처리합니다.
- 예외: `patient.specialInfo`
    - 이 필드는 키 누락과 `null`의 의미가 다릅니다.
        - 키 누락: 병원선정서비스가 값을 보내지 않음 → `400 Bad Request`
        - 하위 필드 값 `null`: 해당 없음 (임산부·신생아가 아님)
    - 시스템은 이 정보로 완화할 수 없는 병원 조건('분만 가능')을 정합니다. 그래서 '보내지 않음'을 '해당 없음'으로 처리하지 않습니다.

| 필드 | 타입 | 필수 | 생략 시 처리 | 설명 |
|------|------|------|-------------|------|
| `incidentId` | string | Y | - | 한 번 출동한 구급대가 이송하는 환자 한 명을 식별하는 ID (접수번호, 긴급구조번호 또는 구급보고서번호). 같은 환자에 대한 재추천 요청은 같은 값을 보냄 |
| `requestSeq` | number | Y | - | 같은 `incidentId`의 요청 차수 (1 이상의 정수). 최초 요청은 `1`, 재추천마다 1씩 증가 |
| `requestedAt` | string | Y | - | 요청 시각 (`yyyy-MM-dd HH:mm:ss`) |
| `recommendCount` | number \| null | N | `null` | 추천받을 병원 수 (1 이상의 정수). `null`이면 시스템은 기본값(10개)만큼 추천 |
| `patient` | object | Y | - | 환자 정보 |
| `patient.info` | object | Y | - | 환자 기본 정보 |
| `patient.info.age` | number | Y | - | 환자 나이 (세). 신원 미상 환자는 추정 나이를 입력. 시스템은 15세 미만이면 후보 필터에 '소아응급 진료 가능' 조건을 추가. 외상 환자가 55세 이상이거나 10세 이하이면 응답에 "직접의료지도 필요" 표시를 넣음 |
| `patient.info.sex` | string | N | `null` | 환자 성별 (예: `남`) |
| `patient.info.patientType` | string | N | `null` | 환자 유형 (예: `일반환자`) |
| `patient.chiefComplaint` | string | N | `null` | 환자가 호소하는 주된 증상. 시스템은 이 값을 LLM 입력으로만 사용 |
| `patient.symptoms` | string[] | N | `[]` | 증상 목록. 시스템은 이 값을 LLM 입력으로만 사용 |
| `patient.consciousnessLevel` | string | Y | - | 환자 의식 수준 (예: `명료`). 시스템은 이 값으로 중증외상 여부를 판정 |
| `patient.majorSevereType` | string \| null | N | `null` | 4대 중증 분류 (심정지, 중증외상, 뇌졸중, 심근경색). 해당 없으면 `null`. `null`이면 시스템은 Pre-KTAS로 환자를 분류. 이 4종이 아닌 값이 오면 시스템은 `400 Bad Request`를 반환 |
| `patient.preKtas` | object | Y | - | Pre-KTAS(병원 전 단계 중증도 분류) 평가 결과 |
| `patient.preKtas.assessmentRound` | number | N | `1` | Pre-KTAS 평가 차수 |
| `patient.preKtas.level` | number | Y | - | Pre-KTAS 단계 (1~5, 숫자가 작을수록 중증) |
| `patient.preKtas.assessmentDetail` | string | Y | - | Pre-KTAS 평가 항목 문구 (`연령 구분 - 대분류 - 중분류 - 소분류` 형식). 시스템은 이 문구를 환자 상태 판단 LLM에 넣어 외상 여부, 필수 진료과, 중증외상 기준 항목을 판단 |
| `patient.vitalSigns` | object \| null | N | `null` | 활력징후. `null`이면 시스템은 Pre-KTAS만으로 중증도를 판정하고 "활력징후 없음" 경고를 추가 |
| `patient.vitalSigns.measuredAt` | string \| null | N | `null` | 측정 시각 (`yyyy-MM-dd HH:mm:ss`) |
| `patient.vitalSigns.recordedAt` | string | Y | - | 기록 시각 (`yyyy-MM-dd HH:mm:ss`) |
| `patient.vitalSigns.systolicBpMmHg` | number \| null | N | `null` | 수축기 혈압 (mmHg) |
| `patient.vitalSigns.diastolicBpMmHg` | number \| null | N | `null` | 이완기 혈압 (mmHg) |
| `patient.vitalSigns.pulsePerMin` | number \| null | N | `null` | 맥박 (회/분) |
| `patient.vitalSigns.respiratoryRatePerMin` | number \| null | N | `null` | 호흡수 (회/분) |
| `patient.vitalSigns.bodyTempCelsius` | number \| null | N | `null` | 체온 (℃) |
| `patient.vitalSigns.spo2Percent` | number \| null | N | `null` | 산소포화도 (%) |
| `patient.vitalSigns.bloodGlucoseMgDl` | number \| null | N | `null` | 혈당 (mg/dL) |
| `patient.medicalHistory` | object[] | N | `[]` | 과거 질환 목록. 시스템은 이 값을 LLM 입력으로만 사용 (환자 상태 판단, 최종 선정 근거 작성) |
| `patient.medicalHistory[].diseaseName` | string | Y | - | 질환명 (예: `뇌혈관질환`, `당뇨`, `기타`) |
| `patient.medicalHistory[].detail` | string \| null | N | `null` | 질환 상세 내용. `diseaseName`이 `기타`이면 실제 질환명을 기재 |
| `patient.medications` | array | N | `[]` | 투여 약물 목록. 시스템은 이 값을 LLM 입력으로만 사용 (환자 상태 판단, 최종 선정 근거 작성) |
| `patient.specialInfo` | object | Y | - | 특수 환자 정보. 키 누락과 `null`의 구분은 '필수 여부 규칙'의 예외 항목 참고 |
| `patient.specialInfo.pregnancyInfo` | object \| null | Y | - | 임산부 정보. 임산부가 아니면 `null`. 값이 있으면 시스템은 후보 필터에 '분만 가능' 조건을 추가하고, 환자 상태 판단 LLM에 넣어 임신 20주 이상인지 판단 |
| `patient.specialInfo.newbornInfo` | object \| null | Y | - | 신생아 정보. 신생아가 아니면 `null`. 시스템은 신생아를 우선 고려하지 않으므로 이 값을 사용하지 않음 |
| `patient.remark` | string | N | `null` | 구급대원이 입력한 자유 서술 텍스트 (예: 수용을 거절한 병원, 환자가 희망하는 병원). 시스템은 이 값을 LLM 입력으로만 사용 (환자 상태 판단의 손상기전·신체검사 소견 판단, 최종 선정) |
| `patient.location` | object | Y | - | 환자 위치 |
| `patient.location.longitude` | number | Y | - | 환자 위치 경도 (WGS84, 도 단위 십진수) |
| `patient.location.latitude` | number | Y | - | 환자 위치 위도 (WGS84, 도 단위 십진수) |
| `rejectedHospitals` | object[] | N | `[]` | 같은 `incidentId`의 이전 추천에서 사용자가 명시적으로 거절한 병원의 누적 목록. 거절이 없으면 `[]` |
| `rejectedHospitals[].hospitalName` | string | Y | - | 거절한 병원명. 이전 응답의 `recommendations[].hospitalName` 값을 그대로 사용 |
| `rejectedHospitals[].reason` | string \| null | N | `null` | 거절 사유 (예: `응급실 병상 포화`) |
| `rejectedHospitals[].rejectedAt` | string | Y | - | 거절 시각 (`yyyy-MM-dd HH:mm:ss`) |

**미정 항목:**
- 값 목록: `patient.info.sex`, `patient.info.patientType`, `patient.consciousnessLevel`, `patient.majorSevereType`에 들어갈 수 있는 값 전체
- 객체 구조: `patient.medications`의 원소, `patient.specialInfo.pregnancyInfo`, `patient.specialInfo.newbornInfo`
- `recommendCount`의 상한
- `patient.vitalSigns.measuredAt` 필드를 유지할지
- 필수 여부 확인: 현장에서 `patient.info.age`와 `patient.consciousnessLevel`이 항상 입력되는지
    - 비어서 오는 경우가 있으면 두 필드를 optional로 바꾸고, 시스템은 값이 없을 때 가장 중증인 판정을 적용합니다 (예: 나이가 없으면 '소아응급 진료 가능' 조건을 추가).

---

## 병원 추천 응답 (Recommend Response)

**Response Body:**

```jsonc
{
    "incidentId": "INC-20260831-000123",      // 사건ID
    "requestSeq": 2,                          // 요청차수
    "recommendations": [                      // 추천병원
        {
            "hospitalId": "A1234567",         // 병원ID
            "hospitalName": "△△병원",         // 병원명
            "rank": 1,                        // 순위
            "reason": "정형외과 수술 가능, 응급실 가용 병상 있음, 거리 4.2km"  // 추천근거
        },
        {
            "hospitalId": "B7654321",
            "hospitalName": "□□의료원",
            "rank": 2,
            "reason": "..."
        }
    ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `incidentId` | string | 요청의 `incidentId` |
| `requestSeq` | number | 이 응답이 대응하는 요청의 `requestSeq` |
| `recommendations` | object[] | 추천 병원 목록. 최대 `recommendCount`개, `rank` 오름차순 |
| `recommendations[].hospitalId` | string | 병원 ID |
| `recommendations[].hospitalName` | string | 병원명. 사용자가 이 병원을 거절하면 다음 요청의 `rejectedHospitals[].hospitalName`에 이 값을 그대로 사용 |
| `recommendations[].rank` | number | 추천 순위 (1부터) |
| `recommendations[].reason` | string | 추천 근거 |

---

## API 요약

| API | Method | Endpoint | 호출 주체 → 처리 주체 |
|-----|--------|----------|----------------------|
| 병원 추천 요청 | `POST` | `/api/v1/recHosp` | 병원선정서비스 → 시스템 |
