# 열려있DOC

> 가장 가까운 곳보다, **내가 도착할 때도 열려 있는 곳**을 찾습니다.

**열려있DOC**은 야간이나 휴일에 이용할 수 있는 병원·약국을 찾는 방문 플래너입니다. 출발 시각과 실제 자동차 이동시간, 공개 운영시간을 함께 계산해 예상 도착 시각에도 운영 중인 후보를 안내합니다. 전국 서비스를 목표로 하며, 첫 검증 지역은 성남 판교입니다.

```text
사용자 요청
  → 출발지 확인
  → 주변 병원·약국과 운영시간 조회
  → 자동차 이동시간 계산
  → 도착 시각 기준 방문 가능 여부 판정
  → 조건을 만족하는 후보 안내 및 방문 계획 저장
```

> [!NOTE]
> FastAPI, SQLite, 방문 계획 CRUD, 판정 로직, 실행 로그, 기본 화면과 함께 외부 Tool 4종 및 LangGraph 추천 흐름이 구현되어 있습니다. 고정 응답 테스트는 통과했으며, 현재 로컬 `.env`에는 외부 서비스 키가 없어 LLM·카카오·국립중앙의료원 실호출 증빙만 대기 중입니다. 키가 없을 때 추천 요청은 임의 결과를 만들지 않고 `setup_required`를 반환합니다.

> [!IMPORTANT]
> 공개 운영시간과 예상 이동시간을 바탕으로 한 방문 안내입니다. 실제 운영 및 접수 여부는 방문 전 기관에 확인해 주세요. 이 서비스는 전문가의 의료 상담을 대신하지 않습니다.

## 서비스 원리

지금 문을 연 가장 가까운 기관도 이동하는 동안 영업이 끝날 수 있습니다. 열려있DOC은 단순한 거리나 현재 영업 여부가 아니라 **도착 시점**을 기준으로 판단합니다.

```text
예상 도착 시각 = 출발 시각 + 자동차 예상 주행시간
```

다음 조건을 모두 만족한 후보만 방문 가능 대상으로 판단합니다.

- 주행시간이 사용자가 정한 최대 이동시간 이내일 것
- 방문일의 운영시간을 확인할 수 있을 것
- `운영 시작 시각 ≤ 예상 도착 시각 < 운영 종료 시각`일 것

마감 시각과 정확히 같은 시각에 도착하는 후보는 제외합니다. 경로 또는 운영시간을 확인할 수 없는 경우에도 값을 추측하지 않고 확인 불가 사유를 남깁니다.

## 프로젝트 구조

`examples/fastapi-basics/`의 `step1_hello.py`~`step5_crud.py`, `app/`, `index.html`, `tools_start.py`는 2026년 11월 18일 오전에 진행한 **FastAPI 학습 예제**입니다. 실제 프로젝트와 섞이지 않도록 한곳에 모았으며, 당시 수정 내용은 그대로 보존했습니다.

열려있DOC의 실제 서비스 코드는 다음 폴더에서 개발합니다.

```text
examples/
  fastapi-basics/    # 오전 FastAPI 학습 예제
backend/
  app/
    agents/          # LLM 분석, LangGraph 실행 흐름, 대화 Memory, 비-LLM 로깅 경계
    api/             # health, chat, plans, logs 라우터
    repositories/    # SQLite 접근
    schemas/         # 요청·응답 모델
    services/        # 시간 판정 등 순수 도메인 로직
    tools/           # 외부 Tool 계약, 카카오·국립중앙의료원 핸들러, 등록부
  scripts/           # 키 설정 후 실행하는 실연동 검증 스크립트
  data/              # 로컬 SQLite 파일(버전 관리 제외)
  tests/
frontend/
  assets/
  index.html
```

## 주요 기능과 구현 상태

| 기능 | 상태 | 설명 |
|---|:---:|---|
| 서버 상태 및 연동 설정 확인 | ✅ | DB와 외부 서비스 키의 설정 여부만 공개 |
| 방문 가능 여부 판정 | ✅ | 이동시간 상한, 마감 경계, 자정을 넘는 운영 구간 처리 |
| 방문 계획 관리 | ✅ | 생성·목록·상세·수정·삭제 및 시간 중복 경고 |
| 실행 로그 관리 | ✅ | 세션별 조회·상세·삭제, 비밀값 형태의 필드 자동 마스킹 |
| 반응형 웹 화면 | ✅ | 채팅 입력, 연동 상태, 저장된 방문 계획 조회·삭제 |
| 외부 Tool 4종 | ✅ | 장소 검색, 주변 기관, `hpid` 상세, 현재·미래 자동차 길찾기 구현 |
| LangGraph 추천 Agent | ✅ | 분석 → 계획 → 실행 → 판단 → 재계획/응답, 대화 Memory와 결과 캐시 구현 |
| 카카오·의료기관 실호출 증빙 | ⏳ | 핸들러 구현 완료, 로컬 키 미설정으로 실데이터 기록 대기 |
| OpenAI 응답·Tool 선택 실증 | ⏳ | 등록 및 모의검증 완료, 로컬 키·모델 미설정으로 실호출 대기 |
| 추천 결과 저장 UI | 🚧 | Agent 연동 후 구현 예정 |

`/api/v1/meta/tools`에서 네 Tool의 사용 시점·입출력·실패 코드와 `implemented: true`를 확인할 수 있습니다. `/api/v1/meta/graph`는 실제 LangGraph 구조를 Mermaid로 반환합니다. 사용법 질문은 외부 Tool 없이 답하고, 추천 요청은 네 연동 설정이 모두 있을 때만 실행됩니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, Uvicorn |
| Database | SQLite |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Test | Python `unittest` |
| External API | Kakao Local, Kakao Mobility, 국립중앙의료원·공공데이터포털 |
| Agent | LangGraph 1.2.10, LangChain 1.3.14, langchain-openai 1.4.3, OpenAI 2.54.0 |

## 사용 예시

```text
성남 판교역 신분당선에서 오늘 밤 9시에 출발해서
차로 20분 안에 도착할 수 있는 약국을 찾아줘.
```

연동 키가 설정되면 기관명·주소, 예상 주행시간과 도착 시각, 방문일의 공개 운영시간, 후보 선택 근거를 함께 안내합니다. 조건을 만족하는 후보가 없으면 탐색 범위와 제외 사유를 설명합니다.

## 로컬 실행

Python 3.12 환경을 권장합니다. PowerShell에서 저장소 루트를 기준으로 실행합니다.

### 1. 환경 준비

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

`.env`가 이미 있다면 마지막 명령은 생략합니다. 서버·계획·로그·사용법 기능은 외부 API 키 없이 실행할 수 있고, 추천 기능은 키가 없으면 필요한 변수명만 안내합니다.

### 2. 백엔드 실행

```powershell
python -m uvicorn backend.app.main:app --reload
```

- API: <http://localhost:8000>
- 웹 화면: <http://localhost:8000/app/>
- Swagger 문서: <http://localhost:8000/docs>
- 상태 확인: <http://localhost:8000/api/v1/health>

서버는 첫 실행 때 `backend/data/planner.db`를 만듭니다. 이 파일과 `.env`는 Git에 올라가지 않습니다.

### 3. 프론트엔드 별도 실행 (선택)

기본적으로 FastAPI가 `frontend/`를 `/app/`에서 함께 제공하므로 별도 실행은 필요하지 않습니다. 프론트엔드만 독립적으로 확인할 때 다음 명령을 사용합니다.

다른 PowerShell 창에서 실행합니다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m http.server 5500 --directory frontend
```

- 화면: <http://localhost:5500>

## 환경변수

`.env.example`을 복사해 만든 로컬 `.env`에 실제 값을 입력합니다. 키 값은 문서·화면·로그·커밋에 남기지 않습니다.

| 변수 | 기본값 | 용도 |
|---|---|---|
| `APP_ENV` | `local` | 실행 환경 이름 |
| `DATABASE_PATH` | `backend/data/planner.db` | SQLite 파일 경로 |
| `CORS_ORIGINS` | 로컬 프론트 주소 | 허용할 Origin, 쉼표로 구분 |
| `REPLAN_LIMIT` | `5` | 후보 재탐색 횟수 상한 |
| `UPSTREAM_TIMEOUT_SECONDS` | `10` | 외부 API 요청 제한시간 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 비어 있음 | LLM과 사용할 모델 |
| `KAKAO_REST_API_KEY` | 비어 있음 | 카카오 Local·Mobility API |
| `NMC_SERVICE_KEY` | 비어 있음 | 국립중앙의료원·공공데이터포털 API |

환경변수를 바꾼 뒤에는 백엔드 서버를 다시 시작합니다. API는 키 원문을 반환하거나 로그에 기록하지 않고 설정 여부만 보여 줍니다.

## 현재 API

| 메서드 | 경로 | 상태 |
|---|---|---|
| `GET` | `/api/v1/health` | DB와 외부 연동 설정 여부 확인 |
| `GET` | `/api/v1/meta/tools` | Tool 계약과 구현 여부 확인 |
| `GET` | `/api/v1/meta/graph` | LangGraph 노드와 조건 분기 구조 확인 |
| `POST` | `/api/v1/chat` | 사용법 응답 또는 추천 Agent 실행 |
| `POST/GET` | `/api/v1/plans` | 계획 저장·목록 |
| `GET/PATCH/DELETE` | `/api/v1/plans/{id}` | 계획 상세·수정·삭제 |
| `GET` | `/api/v1/logs` | 로그 목록, `session_id` 필터 가능 |
| `GET/DELETE` | `/api/v1/logs/{id}` | 로그 상세·삭제 |

계획 시각은 ISO 8601 형식을 사용합니다. 시간대가 없는 값은 한국 표준시(`UTC+09:00`)로 해석하고, 다른 시간대가 있으면 한국 표준시로 정규화합니다.

## 테스트

의존성을 설치한 가상환경에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

정적 import와 문법도 함께 확인하려면 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend
```

테스트는 도착 시각의 마감 경계, 이동시간 상한, 자정을 넘는 운영 구간, 네 Tool의 정상·실패 형식, `hpid → 상세` 연결, 공휴일 시간 누락, 현재·미래 길찾기 선택, 동명 장소 확인, 재계획과 상한, 대화 Memory와 캐시, 방문 계획 CRUD, 로그 마스킹, API 계약을 검증합니다.

## 오전 실연동 검증

`.env`에 네 연동 값을 설정한 뒤 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.verify_morning
```

스크립트는 다음 증빙을 JSON으로 출력하며 키 원문과 원본 응답은 출력하지 않습니다.

- 일반 요청에 대한 LLM 응답과 “성남 판교역에서 출발할래”의 `search_place` 선택
- 성남 판교역 좌표와 주변 병·의원 1곳의 기관 ID·좌표·운영시간·적용일
- 목록의 `hpid`와 상세 응답의 기관 ID 일치 여부
- 2026-12-25 공휴일 운영시간이 확인되는 기관 또는 `확인 필요` 상태
- 즉시 출발 자동차 길찾기 결과

현재 저장소의 로컬 `.env`에는 `OPENAI_API_KEY`, `OPENAI_MODEL`, `KAKAO_REST_API_KEY`, `NMC_SERVICE_KEY`가 비어 있으므로 실호출 결과는 아직 기록하지 않았습니다.

## 로드맵

1. 로컬 키를 설정하고 오전 실연동 검증 결과 기록
2. 추천 결과의 계획 저장 버튼과 계획 수정 화면 연결
3. 대표 시나리오 5개를 고정 응답 재생과 실호출로 나눠 증빙
4. `/docs`, LangGraph 구조, 재계획 로그와 화면 캡처 정리

## 참고 문서

- [주제 정의서](./야간휴일_병원약국_방문플래너_주제정의서.md)
- [1일 차 검증 기록](./전국_야간휴일_병원약국_방문플래너_1일차_검증기록.md)
- [2일 차 작업 체크리스트](./전국_야간휴일_병원약국_방문플래너_2일차_작업체크리스트.md)
- [검증·디버깅 계획](./전국_야간휴일_병원약국_방문플래너_검증_디버깅_계획.md)

