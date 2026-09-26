# API 명세서

> 열려있DOC · AI 코어 프로젝트 3회차 · 기준 코드: `backend/app/api/`, `backend/app/schemas/` (2026-11-20)
> 화면 캡처: `docs/images/07-api-docs.png` (FastAPI `/docs`)

## 1. 공통

| 항목 | 내용 |
|---|---|
| Base URL | `http://127.0.0.1:8000/api/v1` |
| 형식 | JSON (UTF-8). 요청·응답 모델은 Pydantic으로 정의 |
| 시각 | ISO 8601. 시간대가 없으면 한국 표준시(+09:00)로 해석하고, 다른 시간대는 KST로 정규화 |
| 화면 | `GET /app/` 에서 같은 서버가 프론트엔드를 제공 |
| 오류 형식 | `{"detail": "메시지"}` (404, 400). 요청 형식 오류는 FastAPI 기본 422 `{"detail": [{loc, msg, type}]}` |

API는 목적별로 경로를 나눕니다: `system`(상태·메타), `chat`(대화), `plans`(계획 관리), `logs`(실행 로그).

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | DB와 외부 연동 설정 여부 |
| GET | `/meta/tools` | 등록된 Tool 명세 |
| GET | `/meta/graph` | LangGraph 구조(Mermaid) |
| POST | `/chat` | 대화 요청 처리 (사용법 안내 또는 추천 Agent 실행) |
| POST | `/plans` | 방문 계획 저장 |
| GET | `/plans` | 방문 계획 목록 |
| GET | `/plans/{plan_id}` | 방문 계획 상세 |
| PATCH | `/plans/{plan_id}` | 방문 계획 수정 |
| DELETE | `/plans/{plan_id}` | 방문 계획 삭제 |
| GET | `/logs` | 실행 로그 목록 |
| GET | `/logs/sessions/{session_id}` | 세션 실행 로그 상세 (실행 순서) |
| GET | `/logs/{event_id}` | 실행 로그 단건 |
| DELETE | `/logs/{event_id}` | 실행 로그 단건 삭제 |

실행 로그에는 수정 API가 없습니다(F3014).

## 2. System

### GET `/health`

```json
{ "status": "ok", "environment": "local", "database": "ready",
  "integrations": { "llm": true, "kakao": true, "medical_data": true } }
```

`integrations`는 키가 설정됐는지 여부만 돌려주고, 키 값은 돌려주지 않습니다.

### GET `/meta/tools`

`{"tools": [ToolDefinition, ...]}`. 항목은 `name`, `description`, `use_when`, `kind`, `parameters`(JSON Schema), `output_schema`, `failure_codes`, `response_envelope`, `implemented`입니다. 상세는 `03_Tool_정의서.md`를 참고하세요.

### GET `/meta/graph`

`{"format": "mermaid", "graph": "..."}`. 원문은 `docs/evidence/langgraph.mmd`, 도식은 `docs/images/08-langgraph.png`에 있습니다.

## 3. Chat

### POST `/chat`

요청 `ChatRequest`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `session_id` | string (1~100) | | 대화 세션 ID. 생략하면 서버가 UUID를 만듦. 같은 값을 보내면 대화 맥락을 이어감 |
| `message` | string (1~4000) | ✅ | 사용자 요청 |

응답 `ChatResponse`

| 필드 | 타입 | 설명 |
|---|---|---|
| `session_id` | string | 세션 ID |
| `request_id` | string | 이번 요청의 실행 ID. 실행 로그 조회에 사용 |
| `status` | `completed` \| `needs_input` \| `setup_required` \| `failed` | 처리 결과 |
| `answer` | string | 최종 응답 문장 (추천 근거, 제외 사유, 의료 안내 포함) |
| `missing_settings` | string[] | `setup_required`일 때 필요한 환경변수 **이름** |
| `tool_calls` | string[] | 실행 순서대로의 Tool 이름. 캐시 재사용은 `이름:cache` |
| `request_context` | object | 분석한 요청 조건 (출발지·좌표, 기관 종류, 출발 시각, 이동시간 상한 등) |
| `recommendation` | object \| null | 선택한 기관과 상세·경로·판단 근거 |
| `plan_draft` | PlanCreate \| null | 바로 저장할 수 있는 계획 초안 |
| `excluded_candidates` | object[] | 제외 후보의 `institution_id`, `name`, `code`, `reason`, `expected_arrival_at` |
| `replan_count` | integer | 재계획 횟수 |

`status` 기준

| 값 | 조건 |
|---|---|
| `completed` | 추천 후보 선택, 또는 사용법 안내처럼 Tool이 필요 없는 요청 |
| `needs_input` | 필수 조건 누락이나 동명 장소로 사용자 확인이 필요 |
| `setup_required` | API 키나 모델 설정 누락. Planner를 실행하지 않음 |
| `failed` | 조건을 충족하는 후보 없음, 재계획 상한 도달, 처리 중 예외 |

예시 (실제 실행, `docs/evidence/scenario-llm-chat-response.json` 일부)

```json
{
  "session_id": "2",
  "request_id": "11a0784a65e4441bbc594dec9e7450f9",
  "status": "completed",
  "tool_calls": ["search_place", "search_nearby_institutions", "get_institution_detail", "get_driving_route", "..."],
  "recommendation": { "name": "다낫는럭스타워약국", "duration_seconds": 214,
    "expected_arrival_at": "2026-11-20T21:03:34+09:00", "decision_code": "selected" },
  "excluded_candidates": [
    { "name": "판교365약국", "code": "route_unavailable",
      "reason": "출발 시각 기준 마감까지 60분 남았지만 차량 경로를 확인할 수 없습니다 (경로 코드 104)." }
  ],
  "replan_count": 3
}
```

## 4. Plans

### 계획 모델 `PlanCreate`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `institution_type` | `hospital` \| `pharmacy` | ✅ | |
| `institution_id` | string \| null | | hpid |
| `institution_name` | string (1~200) | ✅ | |
| `institution_address` | string (1~500) | ✅ | |
| `visit_date` | date | ✅ | KST 기준 예상 도착 날짜와 같아야 함 |
| `origin_name` | string (1~300) | ✅ | |
| `origin_longitude`, `origin_latitude` | number | ✅ | |
| `destination_longitude`, `destination_latitude` | number | ✅ | |
| `departure_at` | date-time | ✅ | |
| `expected_arrival_at` | date-time | ✅ | 출발 + 주행시간과 1초 이내로 일치해야 함 |
| `travel_duration_seconds` | integer ≥ 0 | ✅ | |
| `operation_start`, `operation_end` | date-time \| null | | 함께 입력하거나 함께 비움. 있으면 `start ≤ 도착 < end` |
| `selection_reason` | string (1~1000) | ✅ | |

`PlanOut`은 위 필드에 `id`, `created_at`, `updated_at`을 더합니다.

### POST `/plans` → 201 `PlanMutationResponse`

```json
{ "plan": { "id": 3, "...": "..." },
  "warnings": ["같은 날짜에 시간이 겹치는 방문 계획이 있습니다."],
  "overlapping_plan_ids": [2] }
```

같은 날짜에 출발~도착 시간이 겹치는 계획이 있어도 저장은 하고, `warnings`와 `overlapping_plan_ids`로 알립니다(F3015).

### GET `/plans?visit_date=YYYY-MM-DD&limit=100` → `PlanOut[]`

`visit_date`로 날짜를 거를 수 있고, `limit`은 1~500입니다.

### GET `/plans/{plan_id}` → `PlanOut` / 404

### PATCH `/plans/{plan_id}` → `PlanMutationResponse`

`PlanUpdate`는 `PlanCreate`의 모든 필드를 선택 입력으로 받습니다. 보낸 필드만 바꾸고, 기존 값과 합친 결과로 시간 관계 규칙을 다시 검사한 뒤 겹침 경고를 다시 계산합니다.

| 상황 | 응답 |
|---|---|
| 성공 | 200 |
| 보낸 필드가 없음 | 400 `변경할 값을 한 개 이상 보내 주세요.` |
| 계획 없음 | 404 |
| 합친 결과가 시간 관계 규칙 위반 (예: 도착이 운영 구간 밖) | 422 `{"detail": "예상 도착 시각이 저장할 운영 구간 안에 있어야 합니다."}`. 계획은 바뀌지 않음 |

### DELETE `/plans/{plan_id}` → 204 / 404

## 5. Logs

### 실행 로그 모델 `ExecutionLogOut`

| 필드 | 설명 |
|---|---|
| `id` | 이벤트 ID (저장 순서) |
| `session_id` | 대화 세션 |
| `request_id` | 대화 요청 1건의 실행 ID. 이 기능 이전에 쌓인 로그는 `null` |
| `event_type` | 이벤트 종류 (`02_Agent_설계.md` 5절) |
| `stage` | 발생 단계 |
| `payload` | 이벤트 내용. 키·토큰처럼 보이는 값은 `[REDACTED]` |
| `duration_ms` | 단계·Tool·요청 소요시간 |
| `created_at` | 발생 시각 (UTC) |

### GET `/logs?session_id=&request_id=&order=desc&limit=100`

목록 조회. 기본 정렬은 최신순(`desc`)이고, `order=asc`로 실행 순서 정렬을 씁니다.

### GET `/logs/sessions/{session_id}?request_id=&latest=false`

세션 하나의 전체 실행 기록을 실행 순서(`id` 오름차순)로 돌려줍니다. 다른 세션의 로그는 섞이지 않습니다.

```json
{
  "session_id": "multi",
  "request_id": null,
  "latest_request_id": "b2...",
  "requests": [
    { "request_id": "a1...", "event_count": 60, "started_at": "...", "ended_at": "...", "duration_ms": 6249 },
    { "request_id": "b2...", "event_count": 48, "started_at": "...", "ended_at": "...", "duration_ms": 2242 }
  ],
  "events": [ ExecutionLogOut, "..." ],
  "summary": null
}
```

- `requests`: 같은 세션의 대화 요청별 실행 묶음(오래된 순)
- `request_id=` 또는 `latest=true`: 그 실행의 이벤트만 돌려주고 `summary`를 채움
- `summary`: 화면 표시용 요약 — `status`, `decision`(판단 주체·이유), `stages[]`, `tools[]`(순서·성공·실패 사유·캐시·소요시간·재계획 차수), `timeline[]`(판단 → Tool → 후보 제외 → 재계획 → 선택 순서), 각종 횟수, `stop_reason`, `missing_settings`
- 세션이 없거나, 지정한 `request_id`가 그 세션의 것이 아니면 404

### GET `/logs/{event_id}` → `ExecutionLogOut` / 404

### DELETE `/logs/{event_id}` → 204 / 404

## 6. 화면에서의 호출 순서 (F3018·F3019)

1. `POST /chat` — 처리 중에는 화면에 "처리 중"만 표시
2. `GET /logs/sessions/{session_id}?request_id={응답의 request_id}` — 실제 기록으로 단계 바와 실행 흐름 표시
3. 저장: `POST /plans` (`plan_draft` 사용) → 겹치면 경고 알림
4. 계획 관리: `GET /plans`, `GET /plans/{id}`, `PATCH /plans/{id}`, `DELETE /plans/{id}`

## 7. 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-11-20 | `PATCH /plans/{id}`가 시간 규칙 위반 시 500을 돌려주던 문제 수정. `ValidationError`를 422와 한 문장 `detail`로 변환 (`test_api.py::test_invalid_plan_update_returns_422_and_keeps_plan`) |
