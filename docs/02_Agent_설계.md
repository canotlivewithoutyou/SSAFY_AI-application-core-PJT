# Agent 설계 문서

> 열려있DOC · AI 코어 프로젝트 3회차 · 기준 코드: `backend/app/agents/`, `events.py`, `composition.py`, `services/` (2026-11-20)
> 구조 도식: `docs/images/08-langgraph.png`

## 1. 전체 구조

```text
[프론트엔드 /app]
      │ POST /chat
      ▼
[채팅 서비스 services/chat.py] ── request.received / setup.required / request.completed ──┐
      │ (사용법 질문은 여기서 바로 응답, 키 누락이면 setup_required)                         │
      ▼                                                                                     │
[메인 Agent: LangGraph PlannerAgent] ── stage / tool / 판단 / 후보 / 재계획 이벤트 ──────────┤ publish
      │ Tool 호출                                                                           ▼
      ▼                                                                         [EventBus (in-process)]
[Tool 레지스트리 → 외부 API 4종]                                                            │ subscribe
                                                                                            ▼
                                                                       [로깅 서브 Agent: LoggingAgent] → SQLite execution_logs
```

| 구성 요소 | 파일 | 역할 |
|---|---|---|
| 메인 Agent | `agents/planner.py` | 요청 분석 → 계획 → Tool 실행 → 제약 판단 → 재계획/응답 |
| 요청 분석 LLM | `agents/llm.py` | 구조화 출력으로 조건 추출. 실패하면 규칙 추출로 대체 |
| 규칙 추출 | `agents/parsing.py` | 메시지에 명시된 값만 추출 (출발지, 기관 종류, 시각, 이동시간 상한) |
| 판정 로직 | `services/availability.py` | 도착 시각과 운영 구간 비교 (LLM 미사용) |
| 이벤트 계약·버스 | `events.py` | `ExecutionEvent`, `EventPublisher`, `EventBus`, 비밀값 마스킹 |
| 로깅 서브 Agent | `agents/logging_agent.py` | 이벤트 구독 → SQLite 저장 (LLM 미사용) |
| 조립 | `composition.py` | 버스에 로깅 Agent를 등록하고 Planner에 버스를 주입 |

## 2. 메인 Agent 실행 단계

LangGraph `StateGraph(PlannerState)`로 구성합니다. 노드마다 진입·종료 이벤트와 소요시간을 남기도록 감싸 두었습니다(`_stage_node`).

```text
START → analyze_request → build_plan → execute_tools → judge_constraints ─┬─(respond)→ generate_response → END
                                            ▲                              │
                                            └──────────── replan ◀─(replan)┘
```

| 단계 | 입력 (상태) | 처리 | 출력 (상태) |
|---|---|---|---|
| `analyze_request` | `user_message`, 이전 `parsed_request`, `tool_cache`, `candidates` | LLM 구조화 분석 후 규칙 추출로 덮어씀. 출발 시각이 없고 나머지가 있으면 현재 시각으로 기본값. 출발지가 바뀌면 이전 좌표 삭제. 같은 출발 좌표·기관 종류면 이전 후보 목록 유지 | `parsed_request`, `analysis_source`, `analysis_reason`, 이번 요청용 초기화 값 |
| `build_plan` | `parsed_request` | 필요한 Tool과 순서 결정. 좌표가 없으면 `search_place`, 조건이 모두 있으면 후보·상세·경로·판정 | `plan`(Tool 목록), `missing_fields` |
| `execute_tools` | `plan`, `parsed_request`, `candidates`, `visited_institution_ids`, `tool_cache` | 출발지 검색(동명이면 되묻기) → 누락 조건 확인 → 후보 조회(없을 때만) → 미방문 첫 후보의 상세 → 경로 | `current_candidate`, `current_detail`, `current_route`, `tool_calls`, `tool_cache`, `clarification` 또는 `stop_reason` |
| `judge_constraints` | 현재 후보의 상세·경로, 이동시간 상한 | `evaluate_visit`으로 판정. 선택 또는 제외 사유 기록, 재계획 여부 결정 | `selected_candidate` 또는 `exclusions`, `needs_replan`, `stop_reason` |
| `replan` | `replan_count`, `exclusions` | 재계획 횟수 +1, 현재 후보 정보 비움 | `replan_count` |
| `generate_response` | 전체 상태 | 추천 근거·운영시간·도착 예상·제외 후보·의료 안내 문장 생성 | `final_answer` |

### 사용자 확인이 필요한 경우 (Tool 호출 전에 멈춤)

- 필수 조건(출발지, 기관 종류, 출발 시각, 이동시간 상한) 중 빠진 것이 있으면 그 항목만 되묻습니다. 출발지가 장소명으로 주어졌다면 좌표 확인까지는 먼저 합니다.
- `search_place` 결과가 서로 다른 지역의 같은 이름이면 후보 3곳을 보여 주고 고르게 합니다.

## 3. 제약 판단 계산식 (F3008)

```text
예상 도착 = 출발 시각 + 카카오모빌리티 경로 소요시간(초)
선택 조건 = (주행시간 ≤ 이동시간 상한) AND (운영 시작 ≤ 예상 도착 < 운영 종료)
```

| 판정 코드 | 조건 | 처리 |
|---|---|---|
| `selected` | 위 조건 충족 | 선택. 마감까지 남은 시간도 계산 |
| `travel_limit_exceeded` | 주행시간이 상한 초과 | 제외 |
| `outside_operating_hours` | 도착 시각이 운영 구간 밖 (마감 정각 도착 포함) | 제외 |
| `operating_hours_unknown` | 방문일 운영시간 미확인 | 제외, "확인 필요"로 안내 |
| `route_unavailable` | 경로 소요시간 미확인 | 제외. 확인 가능한 값으로 "출발 시각 기준 마감까지 N분 남음"만 근거로 제시 |

외부 API로 확인할 수 없는 값은 지어내지 않습니다. 직선거리로 주행시간을 추정하지 않고, 평일 운영시간을 휴일에 적용하지 않습니다.

## 4. 계획 수립과 재계획 조건 (F3006, F3009)

| 구분 | 조건 |
|---|---|
| Tool이 필요 없는 요청 | 사용법 질문(`어떻게 써`, `사용법`, `도움말`)은 채팅 서비스가 Planner 전에 바로 안내. Tool 0회 |
| 실행 전에 멈춤 | API 키·모델 누락 → `setup_required` (다시 시도해도 결과가 같으므로 재계획하지 않음) |
| 재계획 함 | 현재 후보를 제외했고, 아직 확인하지 않은 후보가 남았고, `replan_count < REPLAN_LIMIT` |
| 재계획 안 함 | 출발지 검색·후보 조회 실패, 되묻기 필요, 남은 후보 없음, 상한 도달 |
| 상한 | 환경변수 `REPLAN_LIMIT` (기본 5). 도달하면 "재계획 상한 N회에 도달했습니다."와 확인한 후보별 제외 사유로 응답 |
| 재사용 | 같은 인자의 Tool 결과는 `tool_cache`에서 재사용(`tool.cache_hit`). 후보 목록은 출발 좌표·기관 종류가 같으면 다시 조회하지 않음. 이미 확인한 기관은 `visited_institution_ids`로 건너뜀 |

재계획 시에도 출발 시각과 이동시간 상한은 유지하고 다음 후보만 바꿉니다. 후보 목록은 1페이지(거리순)만 사용하므로, 1페이지 후보를 모두 확인하면 "확인할 수 있는 새 후보가 남아 있지 않습니다."로 종료합니다.

## 5. 메인 Agent와 로깅 Agent의 관계 (F3012, F3013)

### 분리 원칙

- Planner는 `EventPublisher.publish(event)`만 호출합니다. `logging_agent`, 저장소, DB 모듈을 import하지 않습니다(테스트가 import 구문을 검사).
- 구독자 등록은 `composition.py`에서만 합니다. 구독자가 0개여도, 구독자가 예외를 던져도 `EventBus`가 격리하므로 메인 응답은 정상 완료됩니다.
- `LoggingAgent`는 이벤트를 받는 즉시 SQLite `execution_logs`에 발생 순서대로 저장합니다. LLM과 외부 API를 호출하지 않고, 이벤트를 요약하거나 고치지 않습니다.
- 이벤트 생성 시점과 저장 시점에 비밀값 마스킹을 두 번 적용합니다(키 이름 기준 + `sk-…`, `Bearer …`, `KakaoAK …`, `serviceKey=…`, 32자 이상 불투명 토큰 값).

### 이벤트 계약

공통 필드: `session_id`, `request_id`, `event_type`, `stage`, `payload`, `duration_ms`, `created_at`

| event_type | 발행 위치 | 주요 payload |
|---|---|---|
| `request.received` / `request.completed` | 채팅 서비스 | 메시지 길이 / `status`, `tool_calls`, `tool_call_count`, `replan_count` + 전체 `duration_ms` |
| `setup.required` | 채팅 서비스 | `missing_settings` (변수 이름만) |
| `stage.entered` / `stage.exited` | 모든 그래프 노드 | 종료 시 `status`, `duration_ms` |
| `llm.decision` / `analysis.completed` | `analyze_request` | `decision_maker`(`llm`/`rules`), `source`, `reason`, `extracted_fields` |
| `plan.created` | `build_plan` | `steps`, `missing_fields` |
| `tool.requested` / `tool.responded` | `execute_tools` | `tool`, `arguments`, `attempt` / `ok`, `error_code`, `error_message` + `duration_ms` |
| `tool.cache_hit` | `execute_tools` | `tool`, `arguments`, `ok`, `attempt` |
| `candidate.selected` / `candidate.excluded` | `judge_constraints` | `institution_id`, `name`, `code`, `reason`, `attempt`, `will_replan`, `stop_reason` |
| `plan.replanned` | `replan` | `replan_count`, `limit`, `reason`, `visited_institution_ids` |
| `response.generated` | `generate_response` | `selected`, `needs_input`, `replan_count`, `stop_reason` |

API 키, 인증 헤더, 외부 API 원본 응답은 이벤트에 넣지 않습니다.

### 실행 단위

- `session_id`: 대화 하나. Memory와 로그 묶음의 기준
- `request_id`: 대화 요청 1건의 실행. `/chat` 응답에 포함되어 화면이 해당 실행의 기록만 조회

## 6. 대화 맥락 (Memory, F3010)

LangGraph `InMemorySaver`에 `thread_id = session_id`로 상태를 보관합니다.

| 보관하고 다음 요청에 쓰는 것 | 매 요청마다 새로 시작하는 것 |
|---|---|
| `parsed_request`(출발지·좌표, 기관 종류, 출발 시각, 이동시간 상한, 공휴일 여부) | `plan`, `missing_fields`, `current_*` |
| `candidates`, `candidate_basis` (출발 좌표·기관 종류가 같을 때만) | `visited_institution_ids`, `exclusions`, `selected_candidate` |
| `tool_cache` (Tool이 정규화한 결과. 외부 API 원본 응답은 아님) | `replan_count`, `tool_calls`, `clarification`, `stop_reason`, `final_answer` |

갱신 방식
- 새 메시지에 명시된 값만 덮어씁니다. 예: "30분 뒤에 출발하면?"은 출발 시각만 이전 값 + 30분으로 바꾸고 출발지·기관 종류·상한은 유지합니다.
- 출발지 문구가 바뀌면 이전 좌표를 지우고 다시 검색합니다.
- Memory는 서버 프로세스 메모리에 있으므로 서버를 재시작하면 사라집니다. 저장한 방문 계획과 실행 로그는 SQLite에 남습니다.

## 7. LLM 호출 조건

| 위치 | 호출 조건 | 호출하지 않는 경우 |
|---|---|---|
| `analyze_request` | `OPENAI_API_KEY`와 `OPENAI_MODEL`이 설정되어 있을 때 요청마다 1회 (구조화 출력 `RequestAnalysis`) | 사용법 질문, 키 누락. 호출이 실패하면 규칙 추출로 대체하고 `rules_fallback`으로 기록 |
| 판정·재계획·응답 생성 | 호출하지 않음 (규칙과 계산) | — |
| 로깅 Agent | 호출하지 않음 | — |

Tool 선택은 LLM이 아니라 `build_plan`이 분석된 조건으로 정합니다. 필요한 Tool 순서가 조건(좌표 유무, 누락 필드)에 따라 정해지는 도메인이라, 같은 입력에 늘 같은 계획이 나오도록 규칙으로 두었습니다. Tool 명세는 LLM 형식(`llm_definitions()`)으로도 등록되어 있어, 모델이 Tool을 고르는지는 `backend.scripts.verify_morning`의 probe로 따로 확인합니다.

LLM이 뽑은 값보다 규칙으로 뽑은 명시값을 우선합니다. LLM이 출발지에 문장 전체를 넣는 경우가 실제 실행에서 관찰됐지만, 규칙 추출값이 덮어써 장소 검색에는 영향이 없었습니다(개선 후보).

## 8. 심화 구조

F3020~F3023(이상 징후 판단, Planner·Worker 분리, RAG Tool, 캘린더 Tool)은 적용하지 않았습니다.
