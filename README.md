# 전국 야간·휴일 병원·약국 방문 플래너

출발 시각과 실제 자동차 이동시간을 함께 계산해, **예상 도착 시각에도 공개 운영시간 안에 있는 병원·약국 후보**를 제안하는 프로젝트입니다. 전국 서비스가 목표이고 첫 검증 지역은 성남 판교입니다.

> 공개 운영시간과 예상 이동시간을 바탕으로 한 방문 안내입니다. 실제 운영 및 접수 여부는 방문 전 기관에 확인해 주세요. 이 서비스는 전문가의 의료 상담을 대신하지 않습니다.

## 폴더 구분

`examples/fastapi-basics/`의 `step1_hello.py`~`step5_crud.py`, `app/`, `index.html`, `tools_start.py`는 2026년 11월 18일 오전에 진행한 **FastAPI 학습 예제**입니다. 실제 프로젝트와 섞이지 않도록 한곳에 모았으며, 당시 수정 내용은 그대로 보존했습니다.

실제 방문 플래너는 다음 폴더에서 개발합니다.

```text
examples/
  fastapi-basics/    # 오전 FastAPI 학습 예제
backend/
  app/
    agents/          # LangGraph 상태 계약, 비-LLM 로깅 경계
    api/             # health, chat, plans, logs 라우터
    repositories/    # SQLite 접근
    schemas/         # 요청·응답 모델
    services/        # 시간 판정 등 순수 도메인 로직
    tools/           # 외부 Tool 계약과 등록부
  data/              # 로컬 SQLite 파일(버전 관리 제외)
  tests/
frontend/
  assets/
  index.html
```

## 오늘 준비된 범위

- `backend/`와 `frontend/` 분리
- `.env` 로컬 파일과 커밋 가능한 `.env.example`, 비밀값·DB·캐시용 `.gitignore`
- FastAPI 앱, CORS, `/docs`, 상태 확인 API
- SQLite 초기화와 방문 계획 생성·목록·상세·수정·삭제
- 시간이 겹치는 방문 계획을 막지 않고 경고하는 저장 응답
- 세션별 실행 로그 목록·상세·삭제 및 비밀값 키 자동 마스킹
- `개점 ≤ 예상 도착 < 마감`, `주행시간 ≤ 상한` 시간 판정 함수
- 장소 검색·주변 기관·기관 상세·자동차 길찾기 Tool 4종의 이름, 설명, 입력 계약
- LangGraph에서 사용할 상태 구조와 로깅 Agent 경계
- 대화/연동 상태/저장 계획을 보여 주는 반응형 프론트엔드 뼈대
- 문서의 시간 경계값과 SQLite 저장소를 재현하는 표준 라이브러리 테스트

LLM, 카카오, 국립중앙의료원 API의 **실제 호출 코드는 아직 연결하지 않았습니다.** `/api/v1/meta/tools`의 `implemented: false`가 현재 상태를 그대로 보여 줍니다. 추천 요청도 가짜 결과를 만들지 않고 `setup_required`로 응답합니다. 사용법 질문만 외부 Tool 호출 없이 답합니다.

## 로컬 실행

PowerShell에서 저장소 루트를 기준으로 실행합니다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --reload
```

- API: <http://localhost:8000>
- Swagger 문서: <http://localhost:8000/docs>
- 상태 확인: <http://localhost:8000/api/v1/health>

다른 터미널에서 프론트엔드를 띄웁니다.

```powershell
.\.venv\Scripts\Activate.ps1
python -m http.server 5500 --directory frontend
```

- 화면: <http://localhost:5500>

서버는 첫 실행 때 `backend/data/planner.db`를 만듭니다. 이 파일과 `.env`는 Git에 올라가지 않습니다.

## 환경변수

로컬 `.env` 파일은 빈 키를 포함한 상태로 준비되어 있습니다. 실제 값을 채우되, 키 값을 문서·화면·로그·커밋에 남기지 않습니다.

| 변수 | 용도 |
|---|---|
| `OPENAI_API_KEY`, `OPENAI_MODEL` | LLM 및 Tool 선택 |
| `KAKAO_REST_API_KEY` | 카카오 로컬·모빌리티 |
| `NMC_SERVICE_KEY` | 국립중앙의료원/공공데이터포털 |
| `DATABASE_PATH` | SQLite 파일 경로 |
| `CORS_ORIGINS` | 허용할 프론트엔드 주소(쉼표 구분) |
| `REPLAN_LIMIT` | 후보 재탐색 상한. 현재 기본값은 5회 |
| `UPSTREAM_TIMEOUT_SECONDS` | 외부 API 요청 제한시간 |

환경변수를 바꾼 뒤에는 개발 서버를 다시 시작합니다.

## 현재 API

| 메서드 | 경로 | 상태 |
|---|---|---|
| `GET` | `/api/v1/health` | DB와 외부 연동 설정 여부 확인 |
| `GET` | `/api/v1/meta/tools` | Tool 계약과 구현 여부 확인 |
| `POST` | `/api/v1/chat` | 사용법 응답 가능, 추천 Agent 연결 전 |
| `POST/GET` | `/api/v1/plans` | 계획 저장·목록 |
| `GET/PATCH/DELETE` | `/api/v1/plans/{id}` | 계획 상세·수정·삭제 |
| `GET` | `/api/v1/logs` | 로그 목록, `session_id` 필터 가능 |
| `GET/DELETE` | `/api/v1/logs/{id}` | 로그 상세·삭제 |

계획 시각은 ISO 8601 형식을 사용합니다. 시간대가 없는 값은 한국 표준시(`UTC+09:00`)로 해석하고, 다른 시간대가 있으면 한국 표준시로 정규화합니다.

## 테스트

추가 패키지 없이 현재 가상환경에서 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

정적 import와 문법도 함께 확인하려면 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend
```

## 다음 구현 순서

1. 실제 API 문서의 요청·응답을 기준으로 Tool 4종 handler 구현
2. 병원 1곳·공휴일 운영 기관 1곳 실호출 검증
3. 선택한 LLM/Agent 라이브러리의 **과제 지정 버전 확인 후** 의존성 추가
4. 요청 분석 → 계획 → Tool 실행 → 조건 판정 → 재계획 → 응답 그래프 연결
5. 추천 결과의 계획 저장 버튼과 계획 수정 화면 연결
6. 고정 응답 재생과 실호출을 구분해 대표 시나리오 5개 증빙

버전이 문서에 명시되지 않은 LLM/Agent 패키지는 임의 버전으로 고정하지 않았습니다. 과제 명세에서 지정 버전을 확인한 뒤 `backend/requirements.txt`에 추가합니다.

## 기준 문서

- [주제 정의서](./야간휴일_병원약국_방문플래너_주제정의서.md)
- [1일 차 검증 기록](./전국_야간휴일_병원약국_방문플래너_1일차_검증기록.md)
- [2일 차 작업 체크리스트](./전국_야간휴일_병원약국_방문플래너_2일차_작업체크리스트.md)
- [검증·디버깅 계획](./전국_야간휴일_병원약국_방문플래너_검증_디버깅_계획.md)

