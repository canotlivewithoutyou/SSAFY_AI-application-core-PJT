# AI 코어 프로젝트 요구사항 갭 분석 및 보완 계획

> 작성일: 2026-11-20 (P0-1~P0-3, P1 검증, P2 문서 초안 반영: 2026-11-20)  
> 기준 문서: `C:\canotlivewithoutyou\AI코어프로젝트_3회차_요구사항정의서.pdf`  
> 대상 프로젝트: 열려있DOC - 전국 야간·휴일 병원·약국 방문 플래너

## 1. 문서 목적

이 문서는 AI 코어 프로젝트 3회차 요구사항과 현재 구현을 대조한 결과를 기록하고, 남은 작업을 일관된 기준으로 이어가기 위한 실행 계획을 정의한다.

다음 세 가지를 구분해서 관리한다.

- **구현 완료**: 요구사항을 만족하는 코드와 자동 검증 근거가 있다.
- **부분 충족**: 기능은 있으나 요구된 구조, 조회 방식 또는 화면 표현이 일부 부족하다.
- **검증 필요**: 코드는 있으나 실제 API, 브라우저, 응답시간 또는 제출 증빙으로 확인하지 않았다.

심화 기능 F3020~F3023은 선택 항목이다. 선택하지 않는다면 미구현이어도 필수 요구사항 누락으로 판정하지 않는다.

## 2. 현재 상태 요약

| 영역 | 현재 판정 | 비고 |
|---|---:|---|
| 필수 기능 F3001~F3019 | 19개 충족 | 실제 API·브라우저로 검증 완료. 계획 수정 500 오류는 수정 완료, 사용성 개선 2건은 `docs/05_검증_결과.md` 10절 |
| 비기능 NF3001~NF3007 | 7개 충족 (NF3005 잠정) | NF3005 기준 p95 10초 이내, 현재 4회 측정 최대 6.2초. 20회 측정으로 확정 예정. NF3007 README에 출처·한도·약관 정리 |
| 심화 기능 F3020~F3023 | 미구현 | 선택 사항 |
| 자동 테스트 | 49건 통과 | 2026-11-20 계획 수정 422 회귀 테스트 추가 후 기준. 아래 작업 기록의 실행 환경 참고 |
| Python 문법 검사 | 통과 | `python -m compileall -q backend` |
| 실제 연동 검증 | 완료 (Tool 선택 probe 제외) | GMS·카카오·국립중앙의료원 실호출 로그 `docs/evidence/`. `verify_morning`의 LLM Tool 선택 probe는 미실행 |
| 대표 시나리오 검증 | 완료 | 5개 모두 실제 API로 통과 |
| 제출용 화면 캡처 | 완료 | `docs/images/` 10장 + LangGraph 도식 |
| 제출 문서 | 초안 완료 (체크리스트 제외) | `docs/01`~`05`. 셀프 체크리스트는 3일 차 오후 제공 후 작성 |

## 3. 필수 기능 요구사항 점검

| ID | 요구사항 | 판정 | 현재 근거 | 남은 작업 또는 완료 기준 |
|---|---|:---:|---|---|
| F3001 | Tool 명세 정의 및 등록 | 충족 | `backend/app/tools/contracts.py`, `registry.py`에 이름·설명·사용 시점·입출력·실패 코드·LLM 스키마 정의 | 실제 모델이 등록된 Tool을 선택한 결과를 증빙으로 남긴다. |
| F3002 | 후보 조회 Tool | 충족 | 주변 병원·약국 조회, 기본 페이지, 기관 ID와 좌표 반환 | 실제 병원·약국 조회 결과와 조회 기준을 기록한다. |
| F3003 | 상세정보 조회 Tool | 충족 | `hpid` 기반 상세 조회, 방문일 운영시간, 값 누락 시 `확인 필요` 처리 | 실제 목록 ID와 상세 ID 일치, 평일·공휴일·시간 누락 사례를 기록한다. |
| F3004 | 보조 정보 검색 Tool | 충족 | 카카오 장소 검색과 자동차 현재/미래 길찾기 구현 | 실제 장소·현재 경로·미래 경로 및 결과 없음 사례를 기록한다. |
| F3005 | 사용자 요청 분석 | 충족 | LLM 구조화 분석과 안전 필드 규칙 추출 병행 | 실제 LLM 요청 분석 결과를 기록한다. |
| F3006 | 작업 계획 수립 | 충족 | `build_plan`에서 필요한 Tool과 실행 순서를 구성하고 불필요한 Tool을 제외 | Tool 불필요 시나리오에서 외부 호출 0회를 증명한다. |
| F3007 | Tool 호출 및 결과 통합 | 충족 | 앞선 Tool 결과를 다음 Tool 인자로 전달하고 실패를 공통 응답으로 처리 | 실제 실행 로그에서 호출 인자 흐름과 실패 후 진행을 확인한다. |
| F3008 | 제약 적합성 판단 | 충족 | 이동시간 상한과 `개점 ≤ 도착 < 마감` 판정, 확인 불가 값 추측 금지 | 실데이터와 고정 경계값 결과를 함께 기록한다. |
| F3009 | 재계획 | 충족 | 다음 후보 탐색, 캐시 재사용, 방문 후보 중복 방지, 횟수 상한 | 대표 재계획·상한 종료 시나리오를 실행하고 로그를 첨부한다. |
| F3010 | 대화 맥락 유지 | 충족 | LangGraph Memory, 후속 요청에서 기존 출발지 유지, 변경 조건만 갱신 | 동일 세션·새 세션 후속 요청 차이를 실행 증빙으로 남긴다. |
| F3011 | 최종 응답 생성 | 충족 | 추천 근거, 운영시간, 예상 도착, 제외 사유, 의료 안내 포함 | 실제 화면에서 문구와 데이터가 일치하는지 확인한다. |
| F3012 | 실행 이벤트 발행 | 충족 | `backend/app/events.py`의 `ExecutionEvent`·`EventPublisher`·`EventBus`. Planner는 `publisher.publish()`만 호출하고 `logging_agent`·저장소·DB를 import하지 않음(`test_events.py`가 AST로 검사) | 실연동 대표 시나리오의 이벤트 로그를 증빙으로 남긴다. |
| F3013 | 로깅 서브 Agent | 충족 | `LoggingAgent`가 `composition.py`에서 버스 구독자로 등록되어 SQLite에 저장. LLM 미사용. 구독자 0개·예외 구독자·저장 경로 오류·구독 해제 테스트 통과 | 없음(실연동 로그 증빙은 P1). |
| F3014 | 실행 로그 조회 및 삭제 | 충족 | `GET /api/v1/logs/sessions/{session_id}`가 `id ASC`로 반환하고 `requests`·`latest_request_id`로 요청별 trace 구분. `request_id` 컬럼은 기존 DB에 자동 추가. 목록에 `order`·`request_id` 옵션. 수정 API 없음 | 없음(실연동 세션 로그 캡처는 P2). |
| F3015 | 계획 저장 및 조회 | 충족 | SQLite 저장, 목록·상세 조회, 생성 일시, 겹침 경고 제공 | 브라우저와 서버 재시작 후 데이터 유지 여부를 증빙한다. |
| F3016 | 계획 수정 및 삭제 | 충족 | PATCH·DELETE와 수정 후 전체 시간 관계 재검증 | 브라우저에서 수정·삭제 후 목록 즉시 반영을 확인한다. |
| F3017 | 백엔드 API 서버 | 충족 | FastAPI, Pydantic, 대화·계획·로그 경로 분리 | `/docs` 실행 화면과 대표 요청·응답 캡처를 남긴다. |
| F3018 | 프론트엔드 화면 | 충족 | 대화 화면과 계획 관리 화면이 백엔드 API를 호출 | 추천→저장→상세→수정→새로고침→삭제 E2E를 검증한다. |
| F3019 | 실행 과정 및 상태 표시 | 충족 | 900ms 타이머 제거. 요청 중에는 중립 "처리 중"만 표시하고, 응답의 `request_id`로 해당 실행의 저장된 이벤트를 조회해 단계·Tool 순서·성공/실패 사유·캐시·후보 제외·재계획 위치를 렌더링 | 실제 키 환경의 브라우저 E2E와 화면 캡처(P1-3, P2-2). |

## 4. 비기능 요구사항 점검

| ID | 요구사항 | 판정 | 남은 작업 또는 완료 기준 |
|---|---|:---:|---|
| NF3001 | API 키 관리 | 충족 | 실제 키가 `.env`에만 있고 Git 및 제출물에 포함되지 않았는지 제출 직전 다시 검사한다. |
| NF3002 | 화면 노출 제한 | 충족 | 실제 키 누락·외부 API 실패를 실행해 키 값과 원본 오류 상세가 화면에 나타나지 않는지 캡처한다. |
| NF3003 | Tool 실패 처리 | 충족 | 고정 응답과 실제 오류 사례에서 서비스가 중단되지 않고 대안 탐색 또는 안전 응답을 하는지 기록한다. |
| NF3004 | 재계획 상한 | 충족 | 설정값과 상한 종료 로그를 제출 증빙에 포함한다. |
| NF3005 | 응답시간 | 충족 (잠정) | 기준: 정상 추천 p95 10초 이내 + 처리 중 표시. 4회 측정 중앙값 약 5.8초, 최대 6.2초. `backend/scripts/measure_response_time.py`로 20회 측정해 p95 확정. 근거는 `docs/05_검증_결과.md` 8절 |
| NF3006 | 모듈 분리 | 충족 | 현재 프론트엔드·백엔드·Agent·Tool·저장소 분리를 유지한다. |
| NF3007 | 출처와 이용 조건 | 충족 | README "API 키 발급과 설정", "외부 API 출처와 이용 조건" (2026-11-20 확인) |

## 5. 우선순위별 보완 작업

### P0. 필수 요구사항 구조 보완

#### P0-1. 이벤트 발행과 로깅 구독 분리

**대상 파일**

- `backend/app/agents/planner.py`
- `backend/app/agents/logging_agent.py`
- 신규 이벤트 계약 모듈(예: `backend/app/events.py`)
- `backend/tests/test_planner.py`
- 필요 시 신규 로깅 테스트

**작업 내용**

1. 이벤트 필드 계약을 별도 모듈로 정의한다.
2. 메인 Agent는 저장 구현을 모르는 이벤트 발행 인터페이스에 이벤트만 전달한다.
3. Logging Agent는 구독자로서 이벤트를 받아 SQLite에 저장한다.
4. 구독자가 없거나 저장 중 예외가 발생해도 메인 Agent 응답은 정상 완료되도록 한다.
5. 단계 진입·종료, Tool 요청·응답·소요시간, LLM 판단과 이유, 후보 제외, 재계획 이벤트를 유지한다.

**진행 상태: 완료 (2026-11-20)**

- 이벤트 계약: `backend/app/events.py` (`EventType`, `ExecutionEvent`, `EventPublisher`, `EventBus`, `sanitize_payload`)
- 구독자: `backend/app/agents/logging_agent.py`의 `LoggingAgent`, `subscribe_logging_agent()`
- 조립: `backend/app/composition.py`의 `get_event_bus()`, `get_planner_agent()`만 발행자와 구독자를 함께 안다.
- 이벤트 종류: `request.received/completed`, `setup.required`, `stage.entered/exited`, `analysis.completed`(규칙)·`llm.decision`(LLM)과 `reason`, `plan.created`, `tool.requested/responded`(`duration_ms`, `ok`, `error_code`, `error_message`), `tool.cache_hit`, `candidate.selected/excluded`, `plan.replanned`, `response.generated`
- 마스킹: 키 이름 기준에 더해 `sk-…`, `Bearer/KakaoAK …`, `serviceKey=…`, 32자 이상 불투명 토큰 값도 이벤트 생성 시점과 저장 시점에 이중으로 가린다.

**완료 기준**

- `planner.py`가 `logging_agent` 구현을 직접 import하지 않는다.
- 로깅 구독자를 제거한 테스트에서 메인 Agent가 정상 응답한다.
- 저장 실패 테스트에서 메인 Agent 응답과 실행 결과가 유지된다.
- 저장된 이벤트에는 세션 ID, 이벤트 유형, 단계, payload, 소요시간, 생성 시각이 존재한다.

#### P0-2. 세션 실행 로그 상세 및 순서 보장

**대상 파일**

- `backend/app/repositories/logs.py`
- `backend/app/api/logs.py`
- `backend/app/schemas/log.py`
- `backend/tests/test_api.py`
- `backend/tests/test_repositories.py`

**작업 내용**

1. 특정 세션의 이벤트를 `id ASC` 또는 `created_at ASC`로 조회한다.
2. 목록 조회와 세션 실행 상세 조회의 목적을 분리한다.
3. 세션 상세 응답에 이벤트 배열과 시작·종료 시각, 총 소요시간을 제공할지 결정한다.
4. 기존 이벤트 단건 조회·삭제와 수정 API 부재를 유지한다.

**진행 상태: 완료 (2026-11-20)**

- `execution_logs.request_id` 컬럼 추가. `initialize_database()`가 `PRAGMA table_info`로 확인 후 없을 때만 `ALTER TABLE`을 실행하므로 기존 DB와 행이 유지된다. 기존 행의 `request_id`는 `NULL`.
- `GET /api/v1/logs/sessions/{session_id}`: 세션 전체 이벤트(`id ASC`), 요청별 실행 목록 `requests`, `latest_request_id`. `?request_id=` 또는 `?latest=true`로 한 요청만 조회하면 `summary`(단계, Tool 목록, timeline, 카운트)를 함께 반환한다.
- `GET /api/v1/logs`: 기본 정렬 `desc` 유지(호환), `order=asc`와 `request_id` 필터 추가.
- 시작·종료 시각과 총 소요시간은 `requests[]` 항목에 제공한다.

**완료 기준**

- 특정 세션의 첫 이벤트부터 마지막 이벤트까지 실행 순서대로 반환된다.
- 서로 다른 세션의 이벤트가 섞이지 않는다.
- 목록·세션 상세·단건·삭제 API 테스트가 통과한다.
- 로그 수정 API가 존재하지 않는다.

#### P0-3. 실제 이벤트 기반 실행 상태 표시

**대상 파일**

- `frontend/assets/app.js`
- `frontend/index.html`
- `frontend/assets/styles.css`
- `backend/app/services/chat.py`
- `backend/app/schemas/chat.py`
- 필요 시 로그/진행상태 API

**작업 내용**

1. 900ms 타이머로 단계를 완료 처리하는 로직을 제거하거나 단순 대기 애니메이션으로 한정한다.
2. 백엔드의 실제 실행 이벤트 또는 완료 응답의 실행 trace를 화면에 반영한다.
3. 단계별 성공·실패, Tool 이름·호출 순서·캐시 재사용, 후보 제외, 재계획 발생 지점을 표시한다.
4. API 키 누락은 설정 안내로 표시하되 키 값은 노출하지 않는다.

**진행 상태: 완료 (2026-11-20, 실제 키 환경 브라우저 확인은 P1-3)**

- `POST /api/v1/chat` 응답에 `request_id` 추가.
- `app.js`: 요청 중에는 중립 상태만 표시 → 응답 후 `/logs/sessions/{session_id}?request_id=…`로 해당 실행의 summary 조회 → 단계 바와 실행 흐름 렌더링. 다른 실행의 응답·trace는 `request_id` 비교와 요청 순번으로 버린다.
- trace 조회 실패 시 단계를 완료로 표시하지 않고 "실행 기록을 불러오지 못했다"고 안내한다.
- 설정 누락 시 환경변수 이름만 표시한다.

**완료 기준**

- 화면의 완료 단계가 실제 실행된 단계와 일치한다.
- 실패한 Tool과 안전한 실패 사유를 구분해 볼 수 있다.
- 첫 후보 제외와 다음 후보 탐색 사이에 재계획 지점이 표시된다.
- Tool 불필요 요청에는 Tool 호출 단계가 실행된 것처럼 표시되지 않는다.

### P1. 실제 연동 및 대표 시나리오 검증

#### P1-1. 실연동 스크립트 실행

**진행 상태: 부분 완료 (2026-11-20)** — 채팅 경로로 모든 Tool과 LLM 분석을 실호출해 확인했습니다. `verify_morning` 스크립트(LLM Tool 선택 probe 포함)는 아직 실행하지 않았습니다. 실행 중 GMS 키 401 문제를 찾아 `OPENAI_API_BASE` 설정으로 해결했습니다.

```powershell
cd C:\canotlivewithoutyou\FastAPI
.\.venv\Scripts\python.exe -m backend.scripts.verify_morning
```

**확인 항목**

- 일반 요청에 대한 OpenAI 응답
- 장소 요청에서 `search_place` Tool 선택
- 카카오 장소 검색
- 병원·약국 후보 조회
- 목록 `hpid`와 상세 ID 일치
- 평일·공휴일 운영시간 또는 `확인 필요`
- 현재·미래 자동차 길찾기
- 키와 외부 API 원본 응답이 출력되지 않는지

**완료 기준**

- 실행 일시와 결과 요약을 별도 검증 결과 문서에 기록한다.
- 실패한 경우 최초로 기대와 달라진 값, 원인, 수정, 재검증 결과를 남긴다.

#### P1-2. 대표 시나리오 5개 검증

**진행 상태: 완료 (2026-11-20)** — 5개 모두 실제 API로 통과. 결과와 차이·원인은 `docs/05_검증_결과.md` 2절, 원본 로그는 `docs/evidence/`.

| 시나리오 | 방식 | 필수 기록 |
|---|---|---|
| 정상 추천 | 실호출 또는 승인된 고정 응답 | 입력, 최종 추천, 실행 로그, 처리시간 |
| 재계획 | 첫 후보 마감 후 두 번째 후보 선택 | 제외 이유, 재계획 이벤트, 선택 결과 |
| 재계획 상한 | 모든 후보 조건 미충족 | 상한값, 종료 이유, 실제 재계획 횟수 |
| Tool 실패 후 대안 | 경로 오류 104 후 다음 후보 선택 | 실패 코드, 다음 후보 호출, 최종 결과 |
| Tool 불필요 | 사용법 질문 | Tool 호출 0회, 정상 안내 응답 |

각 시나리오마다 다음을 기록한다.

- 입력 요청
- 기대 동작
- 실제 동작
- 차이와 원인
- `session_id`
- 실행 로그
- 응답시간
- 통과 여부
- 실호출 또는 고정 응답 여부

#### P1-3. 브라우저 E2E 검증

**진행 상태: 완료 (2026-11-20)** — 9단계 모두 통과. 기록 `docs/evidence/e2e-browser.md`, 캡처 `docs/images/`.

**실행 명령**

```powershell
cd C:\canotlivewithoutyou\FastAPI
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

**검증 순서**

1. `/app/`에서 추천 요청을 실행한다.
2. 추천 결과를 계획으로 저장한다.
3. 계획 목록과 상세를 확인한다.
4. 계획을 수정하고 목록 반영을 확인한다.
5. 브라우저를 새로고침하고 데이터가 유지되는지 확인한다.
6. 서버를 재시작하고 데이터가 유지되는지 확인한다.
7. 같은 날짜에 겹치는 계획을 저장해 경고를 확인한다.
8. 계획을 삭제하고 목록 반영을 확인한다.
9. API 키 누락과 Tool 실패 화면을 확인한다.

### P2. 제출 문서와 저장소 정리

#### P2-1. 제출 문서 작성

**진행 상태: 초안 완료 (셀프 체크리스트 제외)** — `docs/01_요구사항_정의서.md`, `02_Agent_설계.md`, `03_Tool_정의서.md`, `04_API_명세서.md`, `05_검증_결과.md`.

다음 문서를 저장소에 추가하거나 기존 문서를 제출 형식으로 확장한다.

- 요구사항 정의서: F3001~F3019와 NF3001~NF3007의 프로젝트 적용 내용
- Agent 설계 문서: 실행 단계, 입출력, Memory, 재계획, 이벤트 흐름
- Tool 정의서: Tool별 명세, 사용 시점, 실패 코드, 등록·확장 방법
- API 명세서: 경로, 메서드, 요청·응답 예시, 오류 형식
- 검증 결과서: 대표 시나리오, 실제 결과, 세션 ID, 실행 로그, 응답시간
- 공식 셀프 체크리스트

#### P2-2. 화면 캡처

**진행 상태: 완료** — `docs/images/01`~`10`, LangGraph 도식 `08-langgraph.png`.

- FastAPI `/docs`
- LangGraph 구조
- 정상 추천 화면
- 첫 후보 제외와 재계획 화면
- Tool 실패 안내 화면
- 계획 목록·상세·수정·겹침 경고 화면
- 대표 요청의 전체 실행 로그

캡처에는 API 키, 인증 헤더, 원본 외부 응답, 개인 식별 정보가 포함되지 않아야 한다.

#### P2-3. README 보완

**진행 상태: 완료** — 키 발급·설정, 출처·이용 조건, 필수·심화 구분, 검증 요약, 제출 문서 링크 추가. `.env.example`에 `OPENAI_API_BASE` 안내 추가.

다음 내용을 추가한다.

- API별 발급처와 설정 절차
- API별 공식 출처 링크
- 호출 한도와 이용 조건/약관 링크
- 필수 기능과 선택 심화 기능 구분
- 실제 검증 일시와 검증 범위
- 대표 시나리오와 검증 결과 문서 링크
- 공식 셀프 체크 결과 링크

#### P2-4. Git 저장소 정리

현재 `.gitignore`에 포함되어 있어도 이미 추적 중인 파일은 자동으로 Git 추적에서 제거되지 않는다.

**현재 확인한 항목**

- `.venv`: 약 2,030개 파일, 약 32.7MB가 Git에서 추적 중
- 루트 `__pycache__`: 추적 중
- 사용되지 않는 미추적 이미지 2개 존재
  - `frontend/assets/brand-lockup-transparent.png`
  - `frontend/assets/landing-route-banner-transparent.png`

**정리 원칙**

- 로컬 가상환경은 삭제할 필요 없이 Git 인덱스에서만 제거한다.
- 캐시·컴파일 결과는 제출하지 않는다.
- 미추적 이미지는 사용 여부를 결정한 뒤 커밋하거나 삭제한다.
- `.env`, DB, 실행 로그, 실제 API 키는 커밋하지 않는다.

## 6. 권장 작업 순서

```text
이벤트 계약/구독 구조 보완
  → 세션 로그 순서·상세 API 보완
  → 실제 이벤트 기반 UI trace 보완
  → 자동 테스트 추가 및 전체 회귀 테스트
  → 실연동 스크립트 실행
  → 대표 시나리오 5개 검증
  → 브라우저 E2E 및 응답시간 측정
  → 화면·로그 캡처
  → 제출 문서와 README 갱신
  → Git 저장소 정리
  → 공식 셀프 체크리스트 최종 점검
```

구조 보완 전에 화면 캡처를 만들면 UI와 로그 형식이 바뀐 뒤 다시 촬영해야 하므로, P0 작업을 먼저 완료한다.

## 7. 검증 명령 모음

### 자동 테스트

```powershell
cd C:\canotlivewithoutyou\FastAPI
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

### Python 문법 검사

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend
```

### 실연동 검증

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.verify_morning
```

### 통합 웹 앱 실행

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- 웹 앱: `http://localhost:8000/app/`
- API 문서: `http://localhost:8000/docs`
- 상태 확인: `http://localhost:8000/api/v1/health`
- Tool 명세: `http://localhost:8000/api/v1/meta/tools`
- LangGraph 구조: `http://localhost:8000/api/v1/meta/graph`

## 8. 전체 완료 정의

다음 조건을 모두 충족해야 “필수 요구사항 구현 및 검증 완료”로 표시한다.

- [x] F3001~F3019가 모두 요구 구조와 동작을 만족한다.
- [x] F3012~F3013의 이벤트 발행자와 로깅 구독자가 분리되어 있다.
- [x] 특정 세션 로그를 실행 순서대로 조회할 수 있다.
- [x] UI가 실제 실행 이벤트를 기준으로 단계·Tool 실패·재계획을 표시한다.
- [ ] 자동 테스트와 문법 검사가 통과한다. (재현 환경 49건 통과. Windows `.venv` 재실행 결과 확인 후 체크)
- [x] 실제 OpenAI·Kakao·공공데이터 API 호출 결과가 기록되어 있다. (LLM Tool 선택 probe는 별도 미실행)
- [x] 대표 시나리오 5개의 실제 결과와 세션 로그가 기록되어 있다.
- [x] 대표 요청 응답시간을 측정하고 판단 근거를 남겼다. (p95 확정을 위한 20회 측정은 남음)
- [x] 계획 저장·수정·재시작 후 유지·삭제 E2E가 통과한다.
- [x] 필수 화면과 실행 로그 캡처가 준비되어 있다.
- [x] 요구사항·Agent·Tool·API·검증 결과 문서가 준비되어 있다. (초안)
- [x] README에 실행법, 키 발급/설정, 출처·이용 조건, 문서 링크가 있다.
- [ ] 공식 셀프 체크리스트 점검이 끝났다.
- [ ] `.env`, `.venv`, DB, 캐시, 실제 키가 제출 대상에서 제외되어 있다.
- [ ] 최종 소스와 문서가 제출 저장소에 업로드되어 있다.

## 9. 작업 기록 양식

보완 작업을 수행할 때 아래 표에 한 줄씩 추가한다.

| 날짜 | 요구사항 ID | 작업 내용 | 변경 파일 | 검증 방법 | 결과 | 후속 작업 |
|---|---|---|---|---|---|---|
| 2026-11-20 | 전체 감사 | PDF 요구사항과 현재 코드·테스트·문서 대조 | 이 문서 | 자동 테스트 20건, 문법 검사, 정적 코드 검토 | 보완 항목 확정 | P0-1부터 진행 |
| 2026-11-20 | F3012, F3013 | 이벤트 계약·in-process 버스 분리, Logging Agent를 구독자로 전환, 값 기반 비밀값 마스킹 추가 | `backend/app/events.py`(신규), `backend/app/composition.py`(신규), `agents/planner.py`, `agents/logging_agent.py`, `agents/state.py`, `services/chat.py`, `api/chat.py`, `api/health.py`, `repositories/logs.py`, `tests/test_events.py`(신규), `tests/test_planner.py` | 자동 테스트 48건, compileall | 통과 | 실연동 로그 증빙(P1) |
| 2026-11-20 | F3014 | `request_id` 컬럼·자동 마이그레이션, 세션 상세 API, 목록 정렬·요청 필터 | `database.py`, `repositories/logs.py`, `api/logs.py`, `schemas/log.py`, `schemas/chat.py`, `tests/test_logs_api.py`(신규) | 자동 테스트 48건(기존 DB 마이그레이션 포함) | 통과 | 없음 |
| 2026-11-20 | F3019 | 타이머 제거, 실행별 trace 조회·렌더링, 실패 Tool·제외·재계획 위치 표시 | `services/trace.py`(신규), `frontend/assets/app.js`, `frontend/assets/styles.css`, `tests/test_frontend_contract.py`(신규) | 정적 계약 테스트, 모의 Tool 서버로 로컬 브라우저 스모크(도움말·추천·재계획·후속 캐시·계획 저장·설정 누락) | 통과 | 실제 키 환경 E2E·캡처(P1-3, P2-2) |
| 2026-11-20 | P1 전체 | 실제 API 대표 시나리오 5개, 브라우저 E2E 9단계, 응답시간 측정 | `docs/evidence/`, `docs/images/`, `backend/scripts/run_replan_limit_scenario.py`(.bat) | 실제 GMS·카카오·국립중앙의료원 호출, 사용자 브라우저 조작 | 통과. GMS 401(`OPENAI_API_BASE` 누락)과 서버 창 환경변수 문제 발견·우회 | `verify_morning` probe, 병원·공휴일 실데이터 |
| 2026-11-20 | P2-1~P2-3, NF3005, NF3007 | 제출 문서 초안 5종, README 키 발급·출처·이용 조건, `.env.example` | `docs/01`~`05`, `README.md`, `.env.example`, 이 문서 | 실행 로그 수치 대조, 제공처 페이지 확인(2026-11-20) | 완료 (셀프 체크리스트 제외) | 셀프 체크리스트, Git 정리(P2-4) |
| 2026-11-20 | F3016 | 계획 수정이 시간 규칙을 어기면 500을 돌려주던 문제를 422와 이유 문장으로 수정 | `backend/app/api/plans.py`, `backend/tests/test_api.py`, `docs/04`·`05`, `README.md` | 회귀 테스트, 실제 HTTP 요청(500 → 422) | 통과, 49건 | 없음 |

> 실행 환경 메모: 이번 기록의 테스트(48건, 이후 422 회귀 테스트 추가로 49건)와 compileall은 Windows `.venv`와 같은 버전의 순수 Python 패키지를 Linux Python 3.13에 올린 재현 환경에서 실행했다(컴파일 확장 `orjson`·`ormsgpack`·`xxhash` 등은 동작 호환 대체 모듈 사용). Windows `.venv` 명령으로 한 번 더 실행해 같은 결과를 확인한다.
