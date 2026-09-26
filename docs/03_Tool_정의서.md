# Tool 정의서

> 열려있DOC · 전국 야간·휴일 병원·약국 방문 플래너 · AI 코어 프로젝트 3회차
> 기준 코드: `backend/app/tools/contracts.py`, `registry.py`, `handlers.py` (2026-11-20)

## 1. 개요

메인 Agent가 호출하는 Tool은 외부 API를 감싼 **외부 API 툴 4종**입니다. 로컬 서버 API 툴(일정·문서 검색)은 심화 과제 범위이며 이번 구현에는 없습니다.

| Tool | 분류 | 요구사항 | 감싼 외부 API |
|---|---|---|---|
| `search_place` | 외부 API 툴 | F3004 보조 정보 | 카카오 로컬 키워드 장소 검색 |
| `search_nearby_institutions` | 외부 API 툴 | F3002 후보 조회 | 국립중앙의료원 병·의원/약국 위치정보 조회 |
| `get_institution_detail` | 외부 API 툴 | F3003 상세정보 | 국립중앙의료원 병·의원/약국 기본정보 조회 |
| `get_driving_route` | 외부 API 툴 | F3004 보조 정보 | 카카오모빌리티 자동차 길찾기 / 미래 운행 정보 길찾기 |

모델의 판단이 필요 없는 작업은 Tool로 두지 않습니다. 방문 가능 판정(`services/availability.py`)과 방문 계획 저장은 실행 흐름과 API가 직접 수행합니다.

## 2. 공통 응답 형식

모든 Tool은 예외를 밖으로 던지지 않고 같은 봉투(envelope)로 답합니다.

```json
// 성공
{ "ok": true,  "data": { ... },  "error": null }
// 실패
{ "ok": false, "data": null, "error": { "code": "ROUTE_UNAVAILABLE", "message": "차량 경로를 확인할 수 없습니다 (경로 코드 104)." } }
```

- 핸들러에서 예상하지 못한 예외가 나면 `ToolSpec.invoke()`가 `INTERNAL_ERROR`로, 인자 형식 오류는 `INVALID_INPUT`으로 바꿉니다.
- 실패 메시지는 서비스가 정한 문장으로 만듭니다. 외부 API의 원본 응답 본문과 키는 넣지 않습니다. HTTP 오류는 상태 코드만(`_safe_upstream_message`), 공공데이터 결과 코드 오류는 결과 코드와 짧은 결과 메시지만 덧붙입니다.

### 공통 실패 코드

| 코드 | 의미 | Agent 처리 |
|---|---|---|
| `INVALID_INPUT` | 필수 인자 누락, 형식 오류 | 해당 단계 실패로 기록 |
| `MISSING_API_KEY` | 환경변수 미설정 | 채팅 서비스가 Planner 실행 전에 `setup_required`로 안내 |
| `UPSTREAM_TIMEOUT` | 외부 API 응답 시간 초과 | 실패 사유 기록 후 다음 단계 판단 |
| `UPSTREAM_UNAVAILABLE` | 외부 API 연결 실패 | 동일 |
| `UPSTREAM_HTTP_ERROR` | 외부 API HTTP 오류 | 동일 (상태 코드만 노출) |
| `UPSTREAM_API_ERROR` | 공공데이터 응답의 결과 코드 오류 (예: 인증키 미등록, 일일 호출 한도 초과) | 동일 |
| `INVALID_UPSTREAM_RESPONSE` | 응답을 해석할 수 없음 | 동일 |
| `NO_RESULT` | 결과 없음 | 장소·후보 조회면 종료 사유로 안내 |
| `UNKNOWN_TOOL` | 등록되지 않은 Tool 이름 | 레지스트리가 반환 |

## 3. Tool별 명세

### 3.1 `search_place` — 출발지 좌표 확인

| 항목 | 내용 |
|---|---|
| 사용 시점 (`use_when`) | 출발지가 장소명이나 주소로 주어져 좌표가 필요할 때 |
| 설명 | 장소 후보의 이름, 주소, WGS84 좌표와 동명 장소 여부를 확인한다 |
| 외부 API | `GET https://dapi.kakao.com/v2/local/search/keyword.json` (`size=10`) |

입력

| 이름 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `query` | string | ✅ | 출발지 검색어 (예: `성남 판교역 신분당선`) |
| `region_hint` | string \| null | | 지역 힌트. 있으면 검색어 앞에 붙임 |

출력 `data`

| 필드 | 타입 | 설명 |
|---|---|---|
| `query`, `resolved_query` | string | 요청 검색어와 실제 검색어 |
| `ambiguous` | boolean | 서로 다른 시·도에 같은 이름이 있으면 `true` |
| `candidates[]` | PlaceCandidate | `place_id`, `name`, `address`, `longitude`, `latitude`, `category`, `phone`, `place_url` |
| `source` | string | `Kakao Local keyword search` |

고유 실패: `NO_RESULT`(일치하는 장소 없음).
`ambiguous=true`이면 Agent는 기관 조회를 하지 않고 후보 3곳을 보여 주며 출발지를 되묻습니다.

### 3.2 `search_nearby_institutions` — 주변 병원·약국 후보

| 항목 | 내용 |
|---|---|
| 사용 시점 | 출발 좌표가 확정된 뒤 주변 병원 또는 약국 후보와 hpid가 필요할 때 |
| 설명 | 국립중앙의료원 위치 조회로 거리순 후보와 기관 ID를 반환한다 |
| 외부 API | 약국 `ErmctInsttInfoInqireService/getParmacyLcinfoInqire`, 병원 `HsptlAsembySearchService/getHsptlMdcncLcinfoInqire` |

입력

| 이름 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `longitude` | number (-180~180) | ✅ | 출발 경도 |
| `latitude` | number (-90~90) | ✅ | 출발 위도 |
| `institution_type` | `hospital` \| `pharmacy` | ✅ | 기관 종류 |
| `page` | integer ≥ 1 | | 기본값 1 |

출력 `data`

| 필드 | 설명 |
|---|---|
| `query_origin` | 조회 기준 좌표 |
| `candidates[]` | `institution_id`(hpid), `name`, `address`, `longitude`, `latitude`, `distance_km`, `list_start_time`, `list_end_time` |
| `pagination` | `page`, `page_size`, `total_count` |

- 기준 날짜를 받지 않는 위치 기반 조회입니다. 방문일 기준 운영시간은 다음 Tool에서 확인합니다.
- 좌표나 기관 ID가 없는 항목은 후보에서 뺍니다. 남는 후보가 없으면 `NO_RESULT`입니다.
- `institution_id`가 다음 Tool의 입력이 됩니다.

### 3.3 `get_institution_detail` — 방문일 운영시간

| 항목 | 내용 |
|---|---|
| 사용 시점 | 후보 목록에서 받은 hpid로 방문일에 적용할 상세 운영시간을 확인할 때 |
| 설명 | 기관 상세의 좌표와 요일별 또는 공휴일 운영 구간을 반환하며, 빈 시간은 확인 필요로 둔다 |
| 외부 API | 약국 `getParmacyBassInfoInqire`, 병원 `getHsptlBassInfoInqire` (`HPID` 지정) |

입력

| 이름 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `institution_id` | string | ✅ | 후보 조회에서 받은 hpid |
| `institution_type` | `hospital` \| `pharmacy` | ✅ | 기관 종류 |
| `visit_date` | date (YYYY-MM-DD) | ✅ | 방문일 |
| `is_public_holiday` | boolean \| null | | 공휴일 여부를 명시할 때 |

출력 `data`

| 필드 | 설명 |
|---|---|
| `institution_id`, `name`, `address`, `phone`, `longitude`, `latitude` | 기관 정보 |
| `applied_date`, `applied_day_type` | 적용일과 요일 구분 (`weekday_1`~`weekday_7`, `public_holiday`) |
| `holiday_name`, `holiday_basis` | 공휴일 이름, 판단 근거(`explicit`, `fixed_date`, `weekday_only`) |
| `hours_status` | `confirmed` 또는 `확인 필요` |
| `opening_intervals` | `[{start, end}]` 또는 `null` |
| `source_fields` | 사용한 원본 필드 (예: `dutyTime5s`, `dutyTime5c`) |

판단에 필요한 값이 없을 때의 처리(F3003)
- 해당 요일의 시작·종료 시각이 비어 있으면 `opening_intervals=null`, `hours_status="확인 필요"`로 둡니다. 평일 시간을 휴일에 복사하지 않습니다.
- 종료 시각이 시작보다 이르면 자정을 넘는 구간으로 보고 종료일을 다음 날로 둡니다. `2400`은 다음 날 00:00입니다.
- 공휴일은 날짜가 고정된 공휴일(신정, 삼일절, 어린이날, 현충일, 광복절, 개천절, 한글날, 성탄절)만 자동 판단합니다. 음력·대체 공휴일은 `is_public_holiday=true`가 명시될 때만 공휴일 시간을 씁니다. 응답의 `holiday_basis`로 어떤 기준을 적용했는지 밝힙니다.

고유 실패: `ID_MISMATCH`(요청한 hpid와 일치하는 상세가 없음).

### 3.4 `get_driving_route` — 자동차 예상 주행시간

| 항목 | 내용 |
|---|---|
| 사용 시점 | 기관의 좌표와 출발 시각이 확정되어 자동차 예상 주행시간이 필요할 때 |
| 설명 | 즉시 출발은 자동차 길찾기, 지정한 미래 출발은 미래 운행 정보 길찾기를 선택한다 |
| 외부 API | `GET https://apis-navi.kakaomobility.com/v1/directions` 또는 `/v1/future/directions` |

입력

| 이름 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `origin` | `{longitude, latitude}` | ✅ | 출발 좌표 |
| `destination` | `{longitude, latitude}` | ✅ | 기관 좌표 |
| `departure_at` | ISO 8601 date-time | ✅ | 출발 시각 (시간대 없으면 KST) |

출력 `data`: `mode`(`current`/`future`), `departure_at`, `duration_seconds`, `distance_meters`, `upstream_result_code`, `source`

- 현재 시각 + 30초 이후 출발이면 미래 길찾기를 씁니다.
- 고유 실패: `PAST_DEPARTURE`(현재보다 1분 넘게 과거), `ROUTE_UNAVAILABLE`(경로 결과 없음, 결과 코드 0이 아님, 소요시간 없음).
- 직선거리를 주행시간으로 환산하지 않습니다. 경로를 받지 못하면 Agent는 그 후보를 "경로 확인 불가"로 제외하고, 확인 가능한 값(출발 시각 기준 마감까지 남은 시간)만 근거로 제시합니다.

## 4. Tool 연결 흐름

| 앞선 Tool 출력 | 다음 Tool 입력 |
|---|---|
| `search_place.candidates[0].longitude/latitude` | `search_nearby_institutions.longitude/latitude`, `get_driving_route.origin` |
| `search_nearby_institutions.candidates[i].institution_id` | `get_institution_detail.institution_id` |
| `get_institution_detail.longitude/latitude` (없으면 후보 좌표) | `get_driving_route.destination` |
| 요청 분석의 `departure_at` | `get_institution_detail.visit_date`(날짜 부분), `get_driving_route.departure_at` |

## 5. 등록과 확장 방법

1. `registry.py`의 `TOOL_SPECS`에 `ToolSpec(name, use_when, description, parameters, output_schema, failure_codes)`를 추가합니다. `use_when`에는 기능보다 **언제 쓰는지**를 적습니다.
2. `handlers.py`의 `ExternalToolHandlers`에 같은 이름의 메서드를 만들고, 항상 `success(...)` 또는 `failure(code, message)`를 반환합니다.
3. `build_registry()`가 이름으로 핸들러를 바인딩합니다. Agent에는 `llm_definitions()`(이름·설명·입력 스키마)만 전달하고, 화면과 문서용 목록은 `GET /api/v1/meta/tools`로 확인합니다.
4. 외부 호출은 `http_get`을 주입할 수 있어, 테스트는 실제 API 없이 고정 응답으로 검증합니다(`backend/tests/test_tools.py`).

## 6. 검증 근거

| 항목 | 근거 |
|---|---|
| 등록 목록과 명세 일치 | `GET /api/v1/meta/tools` (Tool 4종, `implemented: true`) |
| 성공·실패 응답 형식, 키 누락 | `test_tools.py::test_missing_keys_return_failure_envelope` |
| 동명 장소 판정 | `test_tools.py::test_place_search_marks_cross_region_name_ambiguous` |
| hpid 연결 | `test_tools.py::test_nearby_hpid_is_passed_to_holiday_detail` |
| 빈 운영시간은 확인 필요 | `test_tools.py::test_empty_holiday_hours_are_check_required` |
| 현재·미래 길찾기 선택 | `test_tools.py::test_route_selects_current_and_future_endpoints` |
| 실제 API 호출 | `docs/evidence/scenario-llm-trace.json` (Tool 10회, 경로 코드 104 실패 포함) |
