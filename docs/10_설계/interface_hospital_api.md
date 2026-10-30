# 병원정보 검색 API 인터페이스

본 문서는 병원정보 검색 API의 인터페이스를 정리합니다. 병원정보 검색 API는 상황판이 쓰는 병원·응급실 조회 기능을 다른 시스템에 제공하는 외부 API입니다. API는 병원 기본 정보와 실시간 데이터(가용병상, 혼잡도, 장비, 중증질환 수용가능 여부, 진료불가 메시지)를 반환합니다.

> 근거: API 제공처가 2026-10-29에 보낸 안내문과, 개발팀이 같은 날 개발서버를 직접 호출해 확인한 결과입니다. 진료불가 메시지는 2026-10-30에 개발서버를 다시 호출해 확인했습니다. 안내문에 없고 개발팀이 직접 호출해서 알아낸 내용에는 **(실측)** 을 붙였습니다.

---

## 목차

1. [공통 사항](#1-공통-사항)
2. [검색 조건 (Query Parameters)](#2-검색-조건-query-parameters)
3. [응급실 목록 (Emergency Rooms)](#3-응급실-목록-emergency-rooms)
4. [응급실 지도 목록 (Emergency Room Map)](#4-응급실-지도-목록-emergency-room-map)
5. [병원 목록 (Hospitals)](#5-병원-목록-hospitals)
6. [병원 지도 목록 (Hospital Map)](#6-병원-지도-목록-hospital-map)
7. [진료과목 (Specialties)](#7-진료과목-specialties)
8. [병원 상세 (Hospital Detail)](#8-병원-상세-hospital-detail)
9. [오류 응답 (Error Response)](#9-오류-응답-error-response)
10. [호출 예시 (curl)](#10-호출-예시-curl)
11. [실측 결과 (2026-10-29, 개발서버)](#11-실측-결과-2026-10-29-개발서버)
12. [미정 항목](#12-미정-항목)
13. [API 요약](#13-api-요약)

---

## 1. 공통 사항

**접속 정보:**

| 항목 | 값 |
|------|-----|
| 서버 | 개발서버 `192.168.1.196`, 포트 `8080`. 운영 서버 주소는 안내받지 않았습니다 |
| 기본 URL | `http://192.168.1.196:8080/aiemd/api/v1/integration/hospitals` |
| Method | `GET` (모든 API) |
| 응답 | UTF-8 JSON |

- API를 호출하는 PC나 서버는 위 주소로 네트워크 접근이 가능해야 합니다. 제공처가 안내한 시험 명령은 프록시를 거치지 않도록(`--noproxy '*'`) 호출합니다.
- 호출하는 쪽은 한글 검색값을 HTTP 클라이언트의 쿼리 파라미터 기능으로 URL 인코딩해서 보냅니다.

**인증 헤더 (모든 요청에 필수):**

| 헤더 | 값 |
|------|-----|
| `X-GGFI-Client-Id` | 제공처가 전달한 `client.json`의 `clientId` 값. 개발서버용 값은 `hospital-partner-dev` |
| `X-GGFI-API-Key` | 제공처가 전달한 `client.json`의 `apiKey` 값 |
| `Accept` | `application/json` |

- 호출하는 쪽은 `X-GGFI-API-Key`에 키 원문을 그대로 넣습니다. `Bearer` 접두어와 따옴표를 붙이지 않습니다.
- 호출하는 쪽은 API 키를 서버 설정에 보관하고, git 저장소나 브라우저 코드에 넣지 않습니다.
- 웹 로그인 정보와 공공데이터 서비스키는 이 API의 인증에 쓰지 않습니다.

**공통 응답 형식:**

```json
{
    "result": "SUCCESS",
    "data": {
        "items": [],
        "totalCount": 0,
        "page": 1,
        "pageSize": 10
    }
}
```

| API 종류 | `data`의 형태 |
|----------|---------------|
| 목록 API (`/emergency-rooms`, 기본 URL) | `items`, `totalCount`, `page`, `pageSize`를 담는 객체. 페이지 방식 |
| 지도 API (`/emergency-rooms/map`, `/map`) | 병원 객체의 배열. 페이지 방식이 아님 |
| 상세 API (`/{id}`) | 병원 한 곳의 객체 |
| 진료과목 API (`/specialties`) | 진료과목 그룹의 배열 |

**공통 필드 규칙:**
- `coordinates`: `[경도, 위도]` 순서의 WGS84 좌표입니다.
- `distance`: 요청의 기준 좌표(`longitude`, `latitude`)에서 병원까지의 거리(km)입니다. 요청에 좌표가 없으면 `null`입니다. **(실측)** 값은 소수 첫째 자리까지 옵니다.
- 병상 수의 `null`: 병원이 그 정보를 제공하지 않았다는 뜻입니다. `null`은 `0`(가용병상 없음)과 뜻이 다릅니다.
- **(실측)** 시각 문자열은 `yyyy-MM-dd HH:mm:ss` 형식입니다.

---

## 2. 검색 조건 (Query Parameters)

아래 표는 목록 API와 지도 API가 받는 검색 조건을 정리합니다.

| 파라미터 | 적용 API | 설명 | 실측 결과 |
|----------|----------|------|-----------|
| `keyword` | 병원·응급실 | 병원명 검색어 | `keyword=아주`로 아주대학교병원 1곳 |
| `sido` | 병원·응급실 | 시·도 | `sido=서울`은 서울특별시 50곳에 분당서울대학교병원(경기도)과 서울산보람병원(울산광역시)을 더한 52곳을 반환했습니다. API가 병원명까지 부분 일치로 찾는 것으로 보이므로, 시·도는 정식 명칭(예: `서울특별시`)으로 보내야 합니다 |
| `sigungu` | 병원·응급실 | 시·군·구 | `sido=경기도&sigungu=수원시`로 7곳 |
| `page` | 목록 API | 페이지 번호. 기본값 `1` | 마지막 페이지를 넘는 `page`를 보내면 `items`는 빈 배열이고 `totalCount`도 `0`으로 옵니다 |
| `pageSize` | 목록 API | 페이지당 건수. 기본값 `20`, 최대 `100` | `101`이면 400 `INVALID_PARAMETER` |
| `longitude`, `latitude` | 병원·응급실 | 기준 좌표 (WGS84 경도·위도). 두 값을 함께 보냅니다 | - |
| `radiusKm` | 병원·응급실 | 반경 (0.1~100km). `longitude`, `latitude`가 필요합니다. 반경 검색을 하면 API는 지역 조건보다 위치 범위를 우선합니다 | 좌표 없이 보내면 400 `INVALID_PARAMETER`. 수원 좌표 반경 10km에 `sido=강원특별자치도`를 함께 보내도 수원 주변 10곳이 가까운 순서로 왔습니다 |
| `specialties` | 병원·응급실 | 진료과목 명칭. 여러 개는 쉼표로 구분. `/specialties`가 반환하는 명칭을 씁니다 | 명칭이 정확히 같아야 합니다. `흉부외과`는 어떤 병원과도 맞지 않고(오류 없이 0건), `심장혈관흉부외과`로 보내야 맞습니다 |
| `specialtyMatchMode` | 병원·응급실 | `ANY`: 하나라도 포함, `ALL`: 모두 포함 | `신경외과,심장혈관흉부외과` + `ALL`로 경기도 응급실 41곳 |
| `availability` | 응급실 | 혼잡 상태: `여유있음`, `보통`, `혼잡`, `정보없음` | 값을 하나만 받습니다. `여유있음,보통`처럼 여러 값을 보내면 400 `INVALID_PARAMETER` |
| `congestionMax` | 응급실 | 최대 혼잡도 (0~100) | `congestionMax=30`으로 경기도 응급실 25곳 |
| `emergencyClasses` | 응급실 | 응급의료기관 등급: `REGIONAL_CENTER`(권역응급의료센터), `LOCAL_CENTER`(지역응급의료센터), `LOCAL_INSTITUTION`(지역응급의료기관). 여러 개는 쉼표로 구분 | 이 세 값 밖의 값을 보내면 400 `REQUEST_REJECTED` |
| `capabilities` | 응급실 | 보유 자원 조건. 여러 개는 쉼표로 구분하고, API는 지정한 조건을 모두 충족하는 병원만 반환합니다 | 받아들인 값: `ER`, `OR`, `CT`, `MRI`, `ANGIOGRAPHY`, `VENTILATOR`, `ECMO`, `CRRT`, `INCUBATOR`, `HYPOTHERMIA`, `OXYGEN`, `DIALYSIS`, `DELIVERY`, `BURN`. 거부한 값(400 `REQUEST_REJECTED`): `ANGIO`, `PEDIATRIC`, `TRAUMA`, `ICU`, `NICU`, `STROKE` 등 |

- **(실측)** 응급실 전용 조건(`availability`, `congestionMax`, `emergencyClasses`, `capabilities`)을 병원 목록 API에 보내면, API는 오류를 내지 않고 그 조건을 무시합니다. 세 조건 모두 경기도 병원 96곳을 그대로 반환했습니다.

---

## 3. 응급실 목록 (Emergency Rooms)

이 API는 응급실을 운영하는 응급의료기관의 목록과 각 기관의 가용병상, 혼잡도를 반환합니다.

**Method:** `GET`

**Endpoint:** `/emergency-rooms`

**Request 예시 (경기도 응급실 10건):**

```
GET /aiemd/api/v1/integration/hospitals/emergency-rooms?sido=경기도&page=1&pageSize=10
```

**Request 예시 (기준 좌표에서 반경 10km):**

```
GET /aiemd/api/v1/integration/hospitals/emergency-rooms?longitude=127.0286&latitude=37.2636&radiusKm=10&page=1&pageSize=20
```

**Response Body (실측, 항목 1개만 남김):**

```json
{
    "result": "SUCCESS",
    "data": {
        "items": [
            {
                "id": "A2100042",
                "name": "의료법인명지의료재단명지병원",
                "type": "권역응급의료센터",
                "region": "고양시",
                "address": "경기도 고양시 덕양구 화수로14번길 55 (화정동)",
                "phone": "031-810-5114",
                "distance": null,
                "status": "여유있음",
                "congestion": 60,
                "capacities": [
                    { "label": "응급실", "current": 6, "total": 15 },
                    { "label": "수술실", "current": 10, "total": 8 },
                    { "label": "중환자실", "current": 17, "total": 24 },
                    { "label": "신생아", "current": 3, "total": 3 },
                    { "label": "입원실", "current": 152, "total": 451 }
                ],
                "lastUpdatedAt": "2026-10-01 16:25:00",
                "statusMessage": null,
                "statusMessageDateTime": null,
                "coordinates": [126.83145733035825, 37.64207169115689],
                "messageCount": 0
            }
        ],
        "totalCount": 73,
        "page": 1,
        "pageSize": 10
    }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `data.items[].id` | string | 병원 ID. 응급의료기관 기관ID(hpid)와 같은 값 **(실측)** |
| `data.items[].name` | string | 병원명 |
| `data.items[].type` | string | 응급의료기관 등급: `권역응급의료센터`, `지역응급의료센터`, `지역응급의료기관` |
| `data.items[].region` | string | 시·군·구 |
| `data.items[].address` | string | 주소 |
| `data.items[].phone` | string | 대표 전화번호 |
| `data.items[].distance` | number \| null | 기준 좌표에서의 거리 (km) |
| `data.items[].status` | string | 혼잡 상태: `여유있음`, `보통`, `혼잡`, `정보없음` |
| `data.items[].congestion` | number \| null | 혼잡도 (0~100). 산출 방식은 안내문에 없습니다. **(실측)** 전국 응급실에서 `여유있음`은 0~60, `보통`은 62~90, `혼잡`은 90~100이었습니다. 90은 `보통`과 `혼잡`에 모두 나왔습니다 |
| `data.items[].capacities` | object[] | 병상 종류별 가용병상 |
| `data.items[].capacities[].label` | string | 병상 종류: `응급실`, `수술실`, `중환자실`, `신생아`, `입원실` |
| `data.items[].capacities[].current` | number \| null | 가용 병상 수. **(실측)** 상세 API의 `availableBeds[].availableCount`와 같은 값입니다. `응급실`은 `hvec`, `수술실`은 `hvoc`, `중환자실`은 `hvicc`(일반 중환자실), `신생아`는 `hvncc`, `입원실`은 `hvgc`의 값입니다 |
| `data.items[].capacities[].total` | number \| null | **(실측)** 상세 API의 `availableBeds[].totalCount`와 같은 값입니다. 뜻은 안내문에 없습니다. 명지병원 수술실은 `current` 10, `total` 8로 `current`가 더 큽니다 |
| `data.items[].lastUpdatedAt` | string | 실시간 데이터 갱신 시각 |
| `data.items[].statusMessage` | string \| null | 진료불가 메시지로 보입니다. **(실측)** 2026-10-30에 메시지가 있는 병원을 포함해 모든 병원에서 `null`이었습니다 |
| `data.items[].statusMessageDateTime` | string \| null | `statusMessage`의 시각으로 보입니다. **(실측)** 모든 병원에서 `null`이었습니다 |
| `data.items[].messageCount` | number | 진료불가 메시지 수입니다. **(실측)** 2026-10-29에는 모든 병원에서 `0`이었습니다. 2026-10-30에는 전국 응급실 414곳 중 120곳이 1 이상이었고, 그 병원 상세의 `statusMessages`와 `publicStatusMessages` 원소 수를 더한 값과 모두 같았습니다 |
| `data.items[].coordinates` | number[] | `[경도, 위도]` |
| `data.totalCount` | number | 검색 조건에 맞는 전체 건수 |
| `data.page` | number | 요청한 페이지 번호 |
| `data.pageSize` | number | 요청한 페이지당 건수 |

- 응급실 목록에는 진료과목(`specialty`) 필드가 없습니다. 그래도 `specialties` 검색 조건은 응급실 목록에서 동작합니다.

---

## 4. 응급실 지도 목록 (Emergency Room Map)

이 API는 지도에 표시할 응급실 목록을 반환합니다. 응답에는 가용병상과 혼잡도가 없습니다.

**Method:** `GET`

**Endpoint:** `/emergency-rooms/map`

**Response Body (실측, 항목 1개만 남김):**

```json
{
    "result": "SUCCESS",
    "data": [
        {
            "id": "A2100042",
            "type": "hospital",
            "name": "의료법인명지의료재단명지병원",
            "category": "종합병원",
            "address": "경기도 고양시 덕양구 화수로14번길 55 (화정동)",
            "phone": "031-810-5114",
            "distance": null,
            "open": true,
            "hours": "24시간 응급진료",
            "emergency": true,
            "coordinates": [126.83145733035825, 37.64207169115689]
        }
    ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `data[].id` | string | 병원 ID (hpid) |
| `data[].type` | string | **(실측)** 항상 `hospital` |
| `data[].name` | string | 병원명 |
| `data[].category` | string | 의료기관 종별. **(실측)** `종합병원`, `병원`, `보건소` |
| `data[].address` | string | 주소 |
| `data[].phone` | string | 대표 전화번호 |
| `data[].distance` | number \| null | 기준 좌표에서의 거리 (km) |
| `data[].open` | boolean | 운영 여부로 보입니다 |
| `data[].hours` | string | 진료 시간 안내 (예: `24시간 응급진료`) |
| `data[].emergency` | boolean | 응급실 운영 여부로 보입니다 |
| `data[].coordinates` | number[] | `[경도, 위도]` |

- `data`는 배열이고 페이지 방식이 아닙니다. **(실측)** `sido=경기도`로 73곳이 한 번에 왔고, 반경 검색(`radiusKm`)도 동작합니다.

---

## 5. 병원 목록 (Hospitals)

이 API는 병원 목록을 반환합니다. 응급실 목록과 달리 응답에 진료과목이 있고, 응급실운영신고기관도 목록에 들어 있습니다.

**Method:** `GET`

**Endpoint:** 기본 URL 그대로 (경로 추가 없음)

**Response Body:** `data`의 형태는 응급실 목록과 같습니다(`items`, `totalCount`, `page`, `pageSize`). `items`의 각 원소는 [병원 상세](#8-병원-상세-hospital-detail)와 같은 필드를 가집니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `data.items[].id` | string | 병원 ID (hpid) |
| `data.items[].name` | string | 병원명 |
| `data.items[].category` | string | 의료기관 종별 (예: `종합병원`, `병원`) |
| `data.items[].emergencyCategory` | string | 응급의료기관 등급. **(실측)** 응급실 목록의 세 등급에 더해 `응급실운영신고기관`이 옵니다 |
| `data.items[].district` | string | 시·군·구 |
| `data.items[].specialty` | string[] | 진료과목 명칭 목록. `/specialties`의 명칭과 같은 값 |
| `data.items[].emergencyPhone` | string | 응급실 전화번호 |
| `data.items[].weeklyHours` | object[] | 요일별 진료 시간 |
| 그 밖의 필드 | - | [병원 상세](#8-병원-상세-hospital-detail)의 필드 표 참고 |

- **(실측)** 경기도 병원 목록은 96곳입니다. 응급실 목록의 73곳에 응급실운영신고기관 23곳을 더한 수입니다. 전국은 535곳입니다.
- **(실측)** 병원 목록의 항목에도 `availableBeds`, `acceptanceCapabilities`, `availableEquipment`, `lastUpdatedAt` 필드가 있지만 값이 비어 있습니다(`availableBeds`의 값은 모두 `- / -`, `acceptanceCapabilities`는 빈 배열, `lastUpdatedAt`은 `null`). 실시간 데이터는 응급실 목록(`capacities`, `status`, `congestion`)과 병원 상세에서만 받을 수 있습니다.

---

## 6. 병원 지도 목록 (Hospital Map)

이 API는 지도에 표시할 병원 목록을 반환합니다.

**Method:** `GET`

**Endpoint:** `/map`

**Response Body:** `data`는 배열이고, 원소의 필드는 [응급실 지도 목록](#4-응급실-지도-목록-emergency-room-map)과 같습니다. **(실측)** `sido=경기도`로 96곳이 한 번에 왔습니다.

---

## 7. 진료과목 (Specialties)

이 API는 `specialties` 검색 조건에 넣을 수 있는 진료과목 명칭을 그룹별로 반환합니다.

**Method:** `GET`

**Endpoint:** `/specialties`

**Response Body (실측, 그룹 1개와 진료과목 2개만 남김):**

```json
{
    "result": "SUCCESS",
    "data": [
        {
            "code": "AM003101",
            "label": "의과",
            "items": [
                { "code": null, "name": "가정의학과", "hospitalCount": 334 },
                { "code": null, "name": "결핵과", "hospitalCount": 7 }
            ]
        }
    ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `data[].code` | string | 그룹 코드. **(실측)** `AM003101`(의과, 29개), `AM003102`(치과, 14개), `AM003103`(한의과, 8개) |
| `data[].label` | string | 그룹 이름 |
| `data[].items[].code` | string \| null | 진료과목 코드. **(실측)** 모두 `null` |
| `data[].items[].name` | string | 진료과목 명칭. `specialties` 검색 조건과 병원의 `specialty`에 쓰는 값 |
| `data[].items[].hospitalCount` | number | 그 진료과목이 있는 병원 수 |

---

## 8. 병원 상세 (Hospital Detail)

이 API는 병원 한 곳의 기본 정보와 실시간 데이터를 반환합니다. 호출하는 쪽은 `{id}`에 다른 조회 API가 반환한 병원 ID를 넣습니다.

**Method:** `GET`

**Endpoint:** `/{id}`

**Response Body (실측, 배열은 원소 1개만 남김):**

```json
{
    "result": "SUCCESS",
    "data": {
        "id": "A2100042",
        "type": "hospital",
        "name": "의료법인명지의료재단명지병원",
        "category": "종합병원",
        "emergencyCategory": "권역응급의료센터",
        "district": "고양시",
        "address": "경기도 고양시 덕양구 화수로14번길 55 (화정동)",
        "phone": "031-810-5114",
        "emergencyPhone": "031-810-5114",
        "distance": null,
        "open": true,
        "hours": "24시간 응급진료",
        "specialty": ["가정의학과"],
        "emergency": true,
        "coordinates": [126.83145733035825, 37.64207169115689],
        "description": "",
        "postalCode": "104-75",
        "fax": "",
        "mapGuide": "",
        "weeklyHours": [
            { "key": "월요일", "label": "월요일", "value": "00:00 ~ 24:00", "available": null, "message": null, "availableCount": null, "totalCount": null }
        ],
        "bedCapacity": [
            { "key": "hperyn", "label": "응급실 병상", "value": "15개", "available": null, "message": null, "availableCount": null, "totalCount": null }
        ],
        "availableBeds": [
            { "key": "hvec", "label": "응급실", "value": "6 / 15", "available": null, "message": null, "availableCount": 6, "totalCount": 15 }
        ],
        "availableFacilities": [
            { "key": "hv42", "label": "분만실", "value": "Y", "available": true, "message": null, "availableCount": null, "totalCount": null }
        ],
        "resuscitationRoom": { "availableCount": 1, "totalCount": 3 },
        "availableEquipment": [
            { "key": "hvctayn", "label": "CT", "value": "Y", "available": true, "message": null, "availableCount": null, "totalCount": null }
        ],
        "acceptanceCapabilities": [
            { "key": "mkioskty1", "label": "심근경색 재관류", "value": "Y", "available": true, "message": null, "availableCount": null, "totalCount": null }
        ],
        "lastUpdatedAt": "2026-10-01 16:25:00",
        "statusMessages": [],
        "publicStatusMessages": [
            { "id": "PUBLIC-590", "message": "본원 CT 고장으로 CT 촬영 불가능.", "messageType": "응급", "symptomTypeCode": "Y000", "symptomTypeName": "응급실", "displayYn": "차단", "displayMethod": "자동", "startDateTime": "20261030122700", "endDateTime": "20261030173000" }
        ]
    }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id`, `type`, `name`, `category`, `address`, `phone`, `distance`, `open`, `hours`, `emergency`, `coordinates` | - | [응급실 지도 목록](#4-응급실-지도-목록-emergency-room-map)과 같습니다 |
| `emergencyCategory`, `district`, `emergencyPhone`, `specialty`, `weeklyHours` | - | [병원 목록](#5-병원-목록-hospitals)과 같습니다 |
| `description`, `postalCode`, `fax`, `mapGuide` | string \| null | 병원 소개, 우편번호, 팩스, 찾아오는 길 |
| `bedCapacity` | object[] | 병상 규모 (항목 객체). 아래 '`bedCapacity` 키' 참고 |
| `availableBeds` | object[] | 가용병상 (항목 객체). 아래 '`availableBeds` 키' 표 참고 |
| `availableFacilities` | object[] | 가용 시설 (항목 객체). **(실측)** `hv42`(분만실) 하나만 나왔고, 전국 응급실 413곳 중 153곳에 있었습니다 |
| `resuscitationRoom` | object \| null | 소생실 병상 `{ "availableCount", "totalCount" }`로 보입니다. **(실측)** 전국 응급실 413곳 중 명지병원 1곳만 값이 있었습니다 |
| `availableEquipment` | object[] | 장비 가용 여부 (항목 객체). 아래 '`availableEquipment` 키' 표 참고 |
| `acceptanceCapabilities` | object[] | 중증질환 수용가능 여부 (항목 객체). 아래 '`acceptanceCapabilities` 키' 표 참고 |
| `lastUpdatedAt` | string \| null | 실시간 데이터 갱신 시각 |
| `statusMessages` | object[] | 진료불가 메시지로 보입니다. **(실측)** 2026-10-29과 2026-10-30 모두 전국 응급실의 모든 병원에서 빈 배열이었습니다. 원소가 `publicStatusMessages`와 같은 구조인지 확인하지 못했습니다 |
| `publicStatusMessages` | object[] | 공개용 진료불가 메시지로 보입니다. 아래 '진료불가 메시지 객체' 참고. **(실측)** 2026-10-29에는 모든 병원에서 빈 배열이었고, 2026-10-30에는 전국 응급실 414곳 중 120곳에 메시지가 모두 734건 있었습니다 |

**항목 객체:** `weeklyHours`, `bedCapacity`, `availableBeds`, `availableFacilities`, `availableEquipment`, `acceptanceCapabilities`의 원소는 모두 같은 구조입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `key` | string | 항목 키. 대부분 국립중앙의료원 응급의료 데이터의 컬럼명과 같습니다 (예: `hvec`, `mkioskty1`) |
| `label` | string | 항목 이름 |
| `value` | string | 화면 표시용 값 (예: `6 / 15`, `Y`, `15개`) |
| `available` | boolean \| null | 가능 여부. `availableEquipment`, `acceptanceCapabilities`, `availableFacilities`에서 씁니다 |
| `message` | string \| null | 항목의 부가 설명. **(실측)** `acceptanceCapabilities`의 영유아·저체중출생아 항목(`mkioskty10`, `mkioskty12`, `mkioskty14`, `mkioskty15`, `mkioskty27`)에만 값이 있었고, 그 밖의 항목은 모두 `null`이었습니다. 아래 `acceptanceCapabilities` 키 설명 참고 |
| `availableCount` | number \| null | 가용 수. `availableBeds`에서 씁니다 |
| `totalCount` | number \| null | 전체 수로 보입니다. `availableBeds`에서 씁니다 |

**진료불가 메시지 객체 (실측, 2026-10-30):** `publicStatusMessages`의 원소입니다. 734건 모두 아래 9개 필드가 있었고, 값이 `null`이거나 빈 문자열인 필드는 없었습니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 메시지 ID (예: `PUBLIC-590`). 병원이 다른 메시지에 같은 `id`가 나오므로, 병원 안에서만 구분되는 값으로 보입니다 |
| `message` | string | 병원이 쓴 메시지 문장. 정해진 형식이 없습니다. 사유 없이 `불가능메세지등록`만 있는 메시지가 97건으로 가장 많았고, `외상성 뇌출혈 수용 가능`처럼 가능한 범위를 알리는 문장도 있었습니다 |
| `messageType` | string | 메시지 구분. `응급`(544건)과 `중증`(190건)이 나왔습니다 |
| `symptomTypeCode` | string | 메시지가 가리키는 대상의 코드. `응급` 메시지는 모두 `Y000`이고, `중증` 메시지는 중증질환 코드(예: `Y0113`)입니다 |
| `symptomTypeName` | string | 메시지가 가리키는 대상의 이름. `응급` 메시지는 모두 `응급실`이고, `중증` 메시지는 중증질환 이름(예: `산부인과 응급(분만)`)입니다 |
| `displayYn` | string | 734건 모두 `차단`이었습니다. 값의 뜻과 나올 수 있는 다른 값은 안내문에 없습니다 |
| `displayMethod` | string | 734건 모두 `자동`이었습니다. 값의 뜻과 나올 수 있는 다른 값은 안내문에 없습니다 |
| `startDateTime` | string | 차단 시작 시각으로 보입니다. `YYYYMMDDHHMMSS` 형식입니다 (예: `20261030122700`) |
| `endDateTime` | string | 차단 종료 시각으로 보입니다. `YYYYMMDDHHMMSS` 형식입니다. 2026-10-30 15:11에 호출했을 때 7건은 이 시각(13:30~15:00)이 이미 지난 메시지였습니다. 시작 시각이 호출 시각보다 늦은 메시지는 없었습니다 |

**`availableBeds` 키 (실측, 모든 병원에 같은 7개):**

| key | label |
|-----|-------|
| `hvec` | 응급실 |
| `hvoc` | 수술실 |
| `hvcc` | 신경과 중환자실 |
| `hvncc` | 신생아 중환자실 |
| `hvccc` | 흉부외과 중환자실 |
| `hvicc` | 일반 중환자실 |
| `hvgc` | 입원실 |

**`bedCapacity` 키 (실측):** `hpbdn`(전체 병상), `dutyhano`(허가 병상), `hperyn`(응급실 병상), `hpgryn`(입원실 병상), `hpicuyn`(일반 중환자실), `hpnicuyn`(신생아 중환자실), `hpopyn`(수술실). 병원마다 들어 있는 키가 다릅니다.

**`availableEquipment` 키 (실측):** `value`는 `Y`, `N`, `N1` 중 하나입니다. `N`과 `N1`의 차이는 안내문에 없습니다.

| key | label |
|-----|-------|
| `hvctayn` | CT |
| `hvmriayn` | MRI |
| `hvangioayn` | 혈관촬영기 |
| `hvventiayn` | 인공호흡기 |
| `hvventisoayn` | 인공호흡기(조산아) |
| `hvincuayn` | 인큐베이터 |
| `hvcrrtayn` | CRRT |
| `hvecmoayn` | ECMO |
| `hvoxyayn` | 고압산소치료기 |
| `hvhypoayn` | 저체온치료기 |
| `hvamyn` | 구급차 |

**`acceptanceCapabilities` 키 (실측):** `value`는 `Y`, `불가능`, `정보미제공` 중 하나입니다. 전국 응급실 413곳의 값 11,508개 중 `Y`가 4,057개, `불가능`이 118개, `정보미제공`이 7,333개였습니다. 영유아·저체중출생아 항목(`mkioskty10`, `mkioskty12`, `mkioskty14`, `mkioskty15`, `mkioskty27`)은 `message`에 병원이 받을 수 있는 연령이나 체중의 제한을 담습니다(예: `연령제한없음`, `1세이상`, `만 4세`, `1800g(32주) 이상`). `value`가 `정보미제공`이어도 `message`에 값이 있는 경우가 있습니다.

| key | label | key | label |
|-----|-------|-----|-------|
| `mkioskty1` | 심근경색 재관류 | `mkioskty15` | 저체중출생아 집중치료 |
| `mkioskty2` | 뇌경색 재관류 | `mkioskty16` | 분만 |
| `mkioskty3` | 거미막하출혈 수술 | `mkioskty17` | 산과수술 |
| `mkioskty4` | 기타 뇌출혈 수술 | `mkioskty18` | 부인과수술 |
| `mkioskty5` | 흉부 대동맥응급 | `mkioskty19` | 중증화상 전문치료 |
| `mkioskty6` | 복부 대동맥응급 | `mkioskty20` | 수족지접합 |
| `mkioskty7` | 담낭질환 | `mkioskty21` | 수족지접합 외 |
| `mkioskty8` | 담도 포함 질환 | `mkioskty22` | 응급투석(HD) |
| `mkioskty9` | 비외상 복부응급수술 | `mkioskty23` | 응급투석(CRRT) |
| `mkioskty10` | 영유아 장중첩·폐색 | `mkioskty24` | 정신과 폐쇄병동 입원 |
| `mkioskty11` | 성인 위장관 응급내시경 | `mkioskty25` | 안과 응급수술 |
| `mkioskty12` | 영유아 위장관 응급내시경 | `mkioskty26` | 성인 영상의학 혈관중재 |
| `mkioskty13` | 성인 기관지 응급내시경 | `mkioskty27` | 영유아 영상의학 혈관중재 |
| `mkioskty14` | 영유아 기관지 응급내시경 | `mkioskty28` | 응급실 |

- **(실측)** 없는 병원 ID(`A9999999`)로 조회하면 API는 404가 아니라 400 `INVALID_PARAMETER`를 반환합니다. 병원 ID는 대소문자를 구분합니다(`a2100002`도 400).

---

## 9. 오류 응답 (Error Response)

**Response Body (실측):**

```json
{
    "message": "Invalid integration credentials",
    "result": "FAIL",
    "errorCodeName": "INVALID_CREDENTIALS"
}
```

| HTTP 상태 | `errorCodeName` | 원인 | 실측 |
|-----------|-----------------|------|------|
| 400 | `INVALID_PARAMETER` | 검색 조건의 형식이나 범위가 틀림 | `pageSize=101`, 좌표 없는 `radiusKm`, 여러 값을 넣은 `availability`, 없는 병원 ID에서 나왔습니다 |
| 400 | `REQUEST_REJECTED` | 안내문에 없음 | `emergencyClasses`와 `capabilities`에 허용하지 않는 값을 넣었을 때 나왔습니다 |
| 401 | `INVALID_CREDENTIALS` | 기관 ID나 API 키가 없거나 맞지 않음 | 인증 헤더를 빼거나 틀린 키를 넣었을 때 나왔습니다 |
| 503 | `API_DISABLED` | 서버에서 API가 비활성화됨 | 확인하지 못했습니다 |
| 500 | - | 서버 오류. 운영자에게 호출 시각과 응답 헤더 `X-Request-Id`를 전달합니다 | 확인하지 못했습니다 |

- **(실측)** API는 성공 응답에도 `X-Request-Id` 헤더와 `Cache-Control: no-store` 헤더를 붙입니다.

---

## 10. 호출 예시 (curl)

아래 명령은 제공처가 안내한 시험 명령이고, 경기도 응급실 10건을 조회합니다.

```bash
curl --noproxy '*' \
  --config /home/wini/ggfi-deploy/hospital-api-credentials-dev/client.curl \
  --connect-timeout 5 \
  --max-time 30 \
  --silent --show-error \
  --get 'http://192.168.1.196:8080/aiemd/api/v1/integration/hospitals/emergency-rooms' \
  --data-urlencode 'sido=경기도' \
  --data-urlencode 'page=1' \
  --data-urlencode 'pageSize=10' \
  --write-out '\nHTTP_STATUS=%{http_code}\n'
```

- `--config`에 넣는 파일에는 아래처럼 인증 헤더 세 줄이 들어갑니다. 제공처가 전달한 `client.json`의 값으로 이 파일을 만들 수 있습니다. 이 파일에는 API 키가 들어 있으므로 권한을 `600`으로 두고 git 저장소 밖에 둡니다.

```
header = "X-GGFI-Client-Id: <client.json의 clientId>"
header = "X-GGFI-API-Key: <client.json의 apiKey>"
header = "Accept: application/json"
```

---

## 11. 실측 결과 (2026-10-29, 개발서버)

| 확인한 것 | 결과 |
|-----------|------|
| 접근 | `192.168.200.171` 서버에서 개발서버로 접근할 수 있습니다 |
| 안내문의 시험 명령 | HTTP 200, 경기도 응급실 전체 73건, 0.07초 |
| 6개 API | 모두 HTTP 200. 응답 시간 0.02~0.15초 (전국 응급실 100건 한 페이지가 0.15초) |
| 조회 범위 | 응급실 목록은 전국 413곳(17개 시·도), 병원 목록은 전국 535곳 |
| 병원 ID | 개발팀이 가진 응급의료기관 기관ID(hpid) 31개를 병원 상세로 모두 조회했습니다. 그래서 API의 병원 ID는 hpid와 같다고 판단했습니다 |
| 병원 상세 반복 호출 | 경기도 응급실 73곳을 하나씩 순서대로 조회하는 데 0.95초, 전국 응급실 413곳은 약 5초가 걸렸습니다 (전국은 응급실 목록 5번 호출 포함) |
| 진료불가 메시지 | 전국 응급실 413곳 모두 `statusMessages`, `publicStatusMessages`가 빈 배열이고 `messageCount`가 `0`입니다. 2026-10-30에 다시 호출했을 때는 414곳 중 120곳의 `publicStatusMessages`에 메시지가 있었습니다. 결과는 [병원 상세](#8-병원-상세-hospital-detail)의 '진료불가 메시지 객체'에 적었습니다 |

---

## 12. 미정 항목

아래 항목은 안내문과 실측으로 확인하지 못했습니다. API 제공처에 확인이 필요합니다.

- 운영 환경: 운영 서버 주소, 운영용 `clientId`와 API 키를 발급받는 절차
- 진료불가 메시지: `statusMessages`와 `publicStatusMessages`의 차이(`statusMessages`는 2026-10-30에도 모든 병원에서 빈 배열), `displayYn`과 `displayMethod` 값의 뜻, 종료 시각이 지난 메시지를 주는 이유, 응급실 목록의 `statusMessage`와의 관계
- 값의 뜻
    - `capacities[].total`과 `availableBeds[].totalCount`가 무엇의 수인지 (`current`보다 작은 경우가 있음)
    - `resuscitationRoom`이 어느 병상의 수인지
    - `availableEquipment`의 `N`과 `N1`의 차이
    - `congestion` 산출 방식과 `status`를 나누는 경계값 (혼잡도 90이 `보통`과 `혼잡`에 모두 나옴)
    - `acceptanceCapabilities`의 `message`가 어떤 항목에 어떤 형식으로 오는지
- `capabilities` 검색 조건이 받는 값의 전체 목록
- `sido` 검색 조건이 병원명까지 부분 일치로 찾는 것이 의도된 동작인지
- 마지막 페이지를 넘는 요청에서 `totalCount`가 `0`으로 오는 것이 의도된 동작인지
- 없는 병원 ID에 404가 아니라 400을 반환하는 것이 의도된 동작인지
- 호출량 제한이 있는지

---

## 13. API 요약

| API | Method | Endpoint | `data` 형태 | 실시간 데이터 |
|-----|--------|----------|-------------|---------------|
| 응급실 목록 | `GET` | `/emergency-rooms` | 페이지 객체 | 가용병상 5종, 혼잡 상태, 혼잡도 |
| 응급실 지도 목록 | `GET` | `/emergency-rooms/map` | 배열 | 없음 |
| 병원 목록 | `GET` | 기본 URL (경로 추가 없음) | 페이지 객체 | 없음 (필드는 있지만 값이 비어 있음) |
| 병원 지도 목록 | `GET` | `/map` | 배열 | 없음 |
| 진료과목 | `GET` | `/specialties` | 배열 | 없음 |
| 병원 상세 | `GET` | `/{id}` | 객체 | 가용병상 7종, 장비, 시설, 중증질환 수용가능 여부, 진료불가 메시지 |
