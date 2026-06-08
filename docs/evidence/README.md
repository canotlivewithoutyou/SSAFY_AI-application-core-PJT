# 검증 증빙 기록

실제 API로 실행한 결과를 보관하는 폴더입니다. 파일마다 무엇을, 언제, 어떻게 실행했는지와 판정 결과를 아래에 기록합니다.

## 파일 목록

| 파일 | 실행 일시 (KST) | 내용 | 관련 요구사항 |
|---|---|---|---|
| `scenario-normal-replan.json` | 2026-11-20 10:25:53 | 정상 추천, 마감으로 재계획, Tool 실패(경로 코드 104) 후 대안 선택 (LLM 인증 실패 상태) | F3005~F3014, F3019, NF3003, NF3005 |
| `scenario-llm-chat-response.json` | 2026-11-20 10:56:24 | GMS 주소 설정 후 같은 요청의 `/chat` 응답 (session `2`) | F3011, F3015(계획 초안) |
| `scenario-llm-trace.json` | 2026-11-20 10:56:24 | 위 요청의 실행 로그. **LLM 분석 경로 확인**, 응답시간 측정 | F3005, F3012~F3014, NF3005 |
| `scenario-no-tool-trace.json` | 2026-11-20 11:02:33 | Tool 불필요 요청(사용법 질문) 실행 로그 | F3006, F3014 |
| `run-session4-limit-not-applied.json` | 2026-11-20 11:10:55 | 재계획 상한 시나리오 1차 시도. `REPLAN_LIMIT=1`이 적용되지 않아 상한 시나리오로는 무효, 응답시간 표본으로만 사용 | NF3005 |
| `run-session4-cache-reuse.json` | 2026-11-20 11:17:32 | 같은 세션(`4`)에서 같은 요청을 다시 보낸 실행. 대화 맥락 유지와 Tool 결과 캐시 재사용 확인 | F3009, F3010, F3014 |
| `run-session5-limit-not-applied.json` | 2026-11-20 11:18:15 | 재계획 상한 시나리오 2차 시도. 여전히 `limit: 5`로 무효, 응답시간 표본으로만 사용 | NF3005 |
| `run-session6-limit-not-applied.json` | 2026-11-20 11:26:42 | 재계획 상한 시나리오 3차 시도. 남은 서버 프로세스(PID 35524)를 종료한 뒤에도 `limit: 5`로 무효, 응답시간 표본으로만 사용 | NF3005 |
| `scenario-replan-limit.json` | 2026-11-20 11:32:16 | **재계획 상한 시나리오.** 서버를 거치지 않고 `backend/scripts/run_replan_limit_scenario.py`로 실행 | F3009, NF3004, F3011, F3014 |

---

## scenario-normal-replan.json

### 실행 방법

1. 서버 실행: `.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000`
2. `/docs`에서 `POST /api/v1/chat` 호출

   ```json
   {
     "session_id": "1",
     "message": "성남 판교역 신분당선에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘"
   }
   ```

3. 응답의 `request_id`로 `GET /api/v1/logs/sessions/1?request_id=942461038d5d4e4a8b46c8c3ffd94da7` 호출
4. 응답 전체를 이 파일로 저장

| 항목 | 값 |
|---|---|
| session_id | `1` |
| request_id | `942461038d5d4e4a8b46c8c3ffd94da7` |
| 외부 API | 카카오 장소 검색, 국립중앙의료원 약국 목록·상세, 카카오 미래 자동차 길찾기 **실호출** |
| LLM | **호출 실패 → 규칙 기반 분석으로 대체** (아래 "한계" 참고) |
| 전체 응답시간 | 3,987ms |
| 이벤트 수 | 60건 |

### 실행 흐름

| 순서 | 후보 | 결과 | 사유 |
|---|---|---|---|
| 1 | 시티약국 | 제외 → 재계획 1회 | 예상 도착 시각이 운영 구간 밖 |
| 2 | 판교365약국 | 제외 → 재계획 2회 | 길찾기 Tool 실패 (경로 코드 104), 마감까지 60분 남은 상태 |
| 3 | 휴베이스알파약국 | 제외 → 재계획 3회 | 예상 도착 시각이 운영 구간 밖 |
| 4 | 다낫는럭스타워약국 | **선택** | 이동시간 상한 이내, 운영 종료 전 도착 예상 |

Tool 호출 10회(캐시 0회, 실패 1회), 재계획 3회, 제외 3곳.

### 이 파일로 확인된 시나리오

| 시나리오 | 판정 | 근거 (파일 내 위치) |
|---|---|---|
| 정상 추천 | 통과 | `summary.selected`, `summary.status = completed` |
| 마감으로 재계획 | 통과 | `timeline`의 `candidate_excluded`(outside_operating_hours) → `replan` |
| Tool 실패 후 대안 | 통과 | `tools[5]`(order 6) `ok=false`, `ROUTE_UNAVAILABLE` → 다음 후보 탐색 |
| 이벤트 발행·저장 (F3012~F3013) | 통과 | 단계 진입·종료 쌍, Tool 요청·응답과 `duration_ms` 기록 |
| 세션 로그 실행 순서 조회 (F3014) | 통과 | `events[].id`가 300 → 359 오름차순 |

### 한계 (재검증 필요)

- **LLM 요청 분석 미검증:** `analysis.completed`의 `source`가 `rules_fallback`입니다. OpenAI 호출이 인증 오류(401)로 실패했고, 명시값 규칙 추출로 대신 처리됐습니다. → `.env`에 `OPENAI_API_BASE`를 설정한 뒤 `scenario-llm-trace.json`에서 해결을 확인했습니다.
- **응답시간:** LLM이 실패해 빨리 끝난 상태에서 잰 값입니다. LLM 호출이 정상이면 분석 단계 시간이 늘어나므로 NF3005는 재측정합니다.
- **실데이터 의존:** 운영시간과 길찾기 결과는 실행 시점마다 달라질 수 있어, 같은 요청을 다시 보내도 결과가 다를 수 있습니다.
- 파일에 API 키, 인증 헤더, 외부 API 원본 응답은 포함되어 있지 않습니다(저장 전 확인).

---

## scenario-llm-chat-response.json

### 배경

`scenario-normal-replan.json`에서 LLM 분석이 401 인증 오류로 실패했습니다. 원인은 SSAFY GMS 키(`S16P…`)를 GMS 중계 주소가 아닌 OpenAI 기본 주소로 보낸 것이었습니다. `.env`에 `OPENAI_API_BASE=https://gms.ssafy.io/gmsapi/api.openai.com/v1`을 추가해 해결했고, 분석 함수 단독 호출에서 정상 응답을 확인했습니다.

### 실행 방법

`POST /api/v1/chat`

```json
{
  "session_id": "2",
  "message": "성남 판교역 신분당선에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘"
}
```

| 항목 | 값 |
|---|---|
| session_id | `2` |
| request_id | `11a0784a65e4441bbc594dec9e7450f9` |
| status | `completed` |
| 선택 결과 | 다낫는럭스타워약국, 주행 3분 34초, 도착 21:03:34, 운영 09:00~22:00 |
| 제외 후보 | 시티약국(운영 구간 밖), 판교365약국(경로 코드 104), 휴베이스알파약국(운영 구간 밖) |
| 재계획 | 3회 |
| 계획 초안(`plan_draft`) | 생성됨 |

session `1`과 같은 후보 순서와 결과가 나와, 실데이터 기준으로 재현성을 확인했습니다.

LLM 분석 경로 사용 여부는 아래 `scenario-llm-trace.json`에서 확인했습니다.

---

## scenario-llm-trace.json

`GET /api/v1/logs/sessions/2?request_id=11a0784a65e4441bbc594dec9e7450f9` 응답 전체입니다.

### LLM 분석 확인 (F3005)

| 항목 | 값 |
|---|---|
| event_type | `llm.decision` (session `1`은 `analysis.completed`) |
| source | `llm+rules` (session `1`은 `rules_fallback`) |
| 판단 이유 | User requested to find a pharmacy within 20 minutes travel from a specific departure location and time. |

판정: **통과.** LLM이 요청을 분석하고, 명시값 규칙으로 보강한 결과가 기록됐습니다.

### 응답시간 (NF3005 측정값 1)

| 구간 | 소요시간 |
|---|---|
| 전체 (`request.completed`) | 6,249ms |
| 요청 분석 (LLM 호출 포함) | 2,115ms |
| 첫 Tool 실행 단계 (장소 검색 + 주변 약국 조회 + 상세 + 경로) | 1,818ms, 이 중 주변 약국 조회 1,070ms |
| 재계획 후 Tool 실행 3회 | 528ms, 490ms, 507ms |
| 판단·재계획·응답 생성 | 각 4~6ms |

- 요청 수신(10:56:24.404)부터 분석 단계 진입(24.986)까지 약 0.58초가 걸렸습니다. 서버 재시작 직후 첫 요청이라 Agent와 LLM 클라이언트를 처음 만드는 시간이 포함된 것으로 보입니다. 반복 측정으로 확인이 필요합니다.
- 가장 큰 비중은 LLM 분석(약 34%)과 외부 Tool 호출입니다.
- 이 값 하나로 판정하지 않고, 반복 측정해 중앙값과 최댓값으로 NF3005를 판단합니다.

### 한계

- 실데이터 기준 결과이며, 같은 요청도 실행 시점에 따라 달라질 수 있습니다.
- LLM이 `origin_query`에 문장 전체를 넣는 경향이 있습니다(분석 함수 단독 호출에서 확인). 현재는 규칙 추출값이 덮어써 장소 검색에 영향이 없지만, 프롬프트 개선 후보로 남깁니다.

---

## scenario-no-tool-trace.json

### 실행 방법

1. `POST /api/v1/chat`

   ```json
   {
     "session_id": "3",
     "message": "이 서비스는 어떻게 써?"
   }
   ```

2. `GET /api/v1/logs/sessions/3?request_id=365a629f1219403086aadff5329cd250` 응답을 저장

### 결과

| 항목 | 값 |
|---|---|
| status | `completed` |
| 이벤트 | `request.received`, `request.completed` 2건뿐 |
| Tool 호출 | `tool_calls: []`, `tool_call_count: 0` |
| Agent 단계 | `stages: []` (LangGraph 단계 미실행) |
| LLM 호출 | 없음 (`decision: null`) |
| 응답시간 | 10ms |

판정: **통과.** 외부 데이터 API(장소, 기관, 경로)와 LLM 모두 호출하지 않고 사용법을 안내했습니다.

### 관찰

- 사용법 질문은 Planner에 들어가기 전에 채팅 서비스가 키워드 규칙(`어떻게 써`, `사용법`, `도움말`, `how to use`)으로 처리합니다. 그래서 "Tool이 필요 없다"는 판단 이유가 로그에 별도로 남지 않습니다.
- 증빙을 보강하려면 이 경로에서 판단 이벤트(예: 어떤 규칙에 해당했는지)를 남기는 개선을 검토할 수 있습니다. 이번 검증의 통과 여부에는 영향이 없습니다.

---

## run-session4-limit-not-applied.json

### 목적과 결과

재계획 상한 시나리오를 위해 `.env`에 `REPLAN_LIMIT=1`을 설정하고 session `4`로 실행했습니다. 그러나 `plan.replanned` 이벤트의 `limit` 값이 `5`로 기록되어, 서버가 바뀐 설정을 읽지 않은 상태였습니다. 결과는 session `2`와 같습니다(재계획 3회 후 다낫는럭스타워약국 선택).

판정: **재계획 상한 시나리오로는 무효.** 원인을 확인한 뒤 다시 실행합니다.

### 재사용 가치

- 같은 요청의 세 번째 재현으로, 후보 순서·제외 사유·선택 결과가 session `1`, `2`와 같습니다.
- NF3005 응답시간 표본 2: 전체 5,618ms, 요청 분석(LLM) 2,050ms, 첫 Tool 실행 1,874ms.

---

## run-session4-cache-reuse.json

session `4`에 두 번째 요청을 보낸 결과입니다. `requests`에 두 실행이 순서대로 나뉘어 기록됐고, 이 파일의 `events`는 두 번째 실행(`7a576636247249149943f521abb336b2`)만 담고 있습니다.

| 항목 | 첫 실행 (11:10:55) | 두 번째 실행 (11:17:32) |
|---|---|---|
| 실행 계획 | `search_place` 포함 5단계 | `search_place` 없이 4단계 |
| LLM 추출 필드 | 출발지 검색어만 | 이전 대화의 출발지 좌표·주소·장소 ID까지 유지 |
| 외부 Tool 실제 호출 | 10회 | **0회** |
| 캐시 재사용 | 0회 | **8회** |
| 전체 응답시간 | 5,628ms | 2,232ms (LLM 1,984ms 제외 시 약 0.25초) |
| 결과 | 다낫는럭스타워약국 | 같음 |

판정:
- **F3010 대화 맥락 유지: 통과.** 같은 세션의 이전 출발지 정보를 유지해 장소 검색을 다시 하지 않았습니다.
- **F3009 캐시 재사용: 통과.** 같은 인자의 기관 상세·경로 결과를 캐시에서 재사용했습니다.
- **F3014 요청 구분: 통과.** 같은 세션의 두 요청이 `request_id`로 구분됩니다.

관찰: 캐시에서 가져온 실패 결과(판교365약국 경로)는 `ok: false`로 표시되지만 `error_code`, `error_message`가 비어 있습니다. 캐시 이벤트에 실패 사유를 함께 남기면 화면에서도 사유를 보여 줄 수 있습니다. 개선 후보로 남깁니다.

---

## run-session5-limit-not-applied.json

새 세션 `5`로 재계획 상한 시나리오를 다시 시도했지만 `plan.replanned`의 `limit`이 여전히 `5`입니다. 재계획 상한 시나리오로는 무효입니다. 설정이 적용되지 않는 원인을 확인 중입니다.

NF3005 응답시간 표본 3: 전체 6,027ms, 요청 분석(LLM) 2,474ms, 첫 Tool 실행 1,845ms.

---

## run-session6-limit-not-applied.json

8000번 포트에 남아 있던 프로세스(PID 35524)를 종료하고 서버를 다시 띄운 뒤 session `6`으로 실행했지만, `plan.replanned`의 `limit`은 여전히 `5`였습니다. 같은 시점에 별도 명령으로 확인한 설정값은 `.env`와 `get_settings()` 모두 `1`이었습니다. 서버 프로세스가 읽는 값과 확인 명령이 읽는 값이 다르다는 뜻이므로, 서버 실행 창의 환경변수와 실행 중인 Python 프로세스 목록을 확인합니다.

NF3005 응답시간 표본 4: 전체 5,666ms, 요청 분석(LLM) 2,022ms, 첫 Tool 실행 1,887ms.

---

## scenario-replan-limit.json

### 실행 방법

서버 실행 창의 환경 문제를 피하려고, 채팅 서비스·LangGraph Planner·실제 Tool·Logging Agent를 한 프로세스에서 실행하는 스크립트를 만들었습니다. 코드 경로는 `/chat` API와 같고 HTTP 계층만 생략합니다. 재계획 상한은 스크립트 안에서 `1`로 고정합니다.

- 스크립트: `backend/scripts/run_replan_limit_scenario.py`
- 실행: `backend/scripts/run_replan_limit_scenario.bat` 더블클릭, 또는 `.\.venv\Scripts\python.exe -m backend.scripts.run_replan_limit_scenario`
- 파일 구성: `chat_response`(채팅 응답), `trace`(세션 로그와 요약), `environment_check`(설정값 출처 확인)

| 항목 | 값 |
|---|---|
| session_id | `scenario-limit-113216` |
| request_id | `5932d75e23ab4459b7fde4024778a558` |
| status | `failed` |
| 기록된 `limit` | `1` |
| replan_count | `1` |
| 제외 후보 | 시티약국(운영 구간 밖), 판교365약국(경로 코드 104) |
| stop_reason | 재계획 상한 1회에 도달했습니다. |
| LLM 분석 | `llm+rules` |
| 외부 Tool 호출 | 6회 |
| 응답시간 | 4,729ms |

판정: **통과.** 첫 후보 제외 후 1회 재계획하고, 두 번째 후보도 제외되자 남은 후보가 있음에도 상한에서 멈췄습니다. 응답에는 종료 사유와 확인한 후보별 제외 이유, 의료 안내 문구가 포함됐습니다.

### 서버에서 상한이 적용되지 않던 문제 (원인 미확정)

| 확인 위치 | `REPLAN_LIMIT` |
|---|---|
| `.env` 파일 | `1` |
| 탐색기에서 실행한 새 프로세스가 물려받은 값 | 없음 |
| 새 프로세스의 설정값 | `1` |
| PowerShell에서 띄운 서버가 기록한 값 | `5` (session 4, 5, 6) |

새 프로세스에서는 `1`이 정상 적용되므로 코드와 `.env`는 원인이 아닙니다. 서버를 띄운 PowerShell 창에 `REPLAN_LIMIT` 환경변수가 남아 있었거나(설정 코드가 `load_dotenv(override=False)`라 이미 있는 환경변수가 `.env`보다 우선), 예전 서버 프로세스가 계속 응답했을 가능성이 큽니다. 확인 당시 PowerShell 창이 여러 개 열려 있었습니다. 서버 기반 재현이 필요하면 새 PowerShell 창에서 서버를 띄워 확인합니다.
