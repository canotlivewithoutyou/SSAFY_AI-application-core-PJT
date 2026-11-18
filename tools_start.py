"""내 도메인 Tool 시작 파일

쓰는 법:
    1. 내 프로젝트 폴더에 tools.py 라는 이름으로 복사한다
    2. .env 에 내 API 키를 넣는다 (예: MY_API_KEY=발급받은_키). 코드에는 적지 않는다
    3. ③ search_items 를 내 도메인 API 에 맞게 고친다 — 이름 · 인자 · 주소 · 뽑을 값
    4. 같은 모양으로 Tool 을 세 개(F3002 · F3003 · F3004)까지 늘리고 ④ TOOLS 에 등록한다
    5. python tools.py  → Tool 목록과 정상 · 실패 결과가 찍히면 오늘의 도착점 (체크리스트 1~4번)

지킬 약속 — 내일 라이브에서 영화 Tool 로 같은 모양을 같이 만듭니다
    · 성공도 실패도 ok() · fail() 로 돌려준다. 예외를 밖으로 던지지 않는다
    · 응답 원본을 통째로 넘기지 않는다. 판단에 쓸 값만 뽑는다
    · 비어 있는 값은 "" 나 0 으로 채우지 않는다
    · 오늘은 LLM · Agent · FastAPI 에 연결하지 않는다. Tool 은 혼자 실행된다

①②④ 는 그대로 두고, 고칠 곳은 ③ 과 맨 아래 시험 호출의 TODO 뿐입니다.
"""
import os
from dataclasses import dataclass
from typing import Callable

import requests
from dotenv import load_dotenv

load_dotenv()             # .env 의 키를 환경변수로 읽는다

# ── ① 약속: 성공도 실패도 같은 모양 ──────────────────────────
def ok(data):
    return {"ok": True, "data": data}

def fail(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}

# 실패 코드 — 내 도메인에 꼭 필요하면 하나씩 더한다 (예: 영화의 NO_RUNTIME)
#   BAD_ARGUMENT    입력이 규격과 다르다 (빈 값 · 형식 틀림 · 모르는 인자)
#   INVALID_KEY     키가 없거나 틀렸다
#   NOT_FOUND       찾는 대상이 없다 (없는 식별자)
#   NO_DATA         조회는 됐지만 결과가 비었다
#   UPSTREAM_ERROR  외부 API 가 응답하지 않았다 (시간 초과 · 서버 오류)

# ── ② Tool 명함: 이름 · 설명 · 입력 규격 · 함수 ──────────────
@dataclass
class Tool:
    name: str             # 이름표
    description: str      # 언제 쓰는지 (모델이 읽는다)
    parameters: dict      # 입력 규격 (JSON Schema)
    func: Callable        # 실제로 일하는 함수

    def run(self, **kwargs):
        try:
            return self.func(**kwargs)
        except TypeError:
            return fail("BAD_ARGUMENT", "입력값이 규약과 다릅니다.")
        except Exception:
            return fail("UPSTREAM_ERROR", "Tool 실행 중 오류입니다.")

# ── ③ 외부 API Tool — 내 도메인에 맞게 고친다 ─────────────────
API_URL = "https://api.example.com/search"     # TODO 내 API 주소
KEY_NAME = "MY_API_KEY"                         # TODO .env 에 둔 키 이름

def search_items(keyword: str):
    if not keyword:
        return fail("BAD_ARGUMENT", "keyword는 필수입니다.")
    key = os.getenv(KEY_NAME)
    if not key:
        return fail("INVALID_KEY", f"{KEY_NAME}가 없습니다.")
    try:
        res = requests.get(API_URL, params={"key": key, "query": keyword},   # TODO 파라미터 이름
                           timeout=10)
        res.raise_for_status()
        body = res.json()
    except requests.RequestException:            # 오류 원문에는 키가 든 주소가 섞인다
        return fail("UPSTREAM_ERROR", "외부 API를 부르지 못했습니다.")
    items = body.get("items", [])                # TODO 내 API 응답 구조에 맞게
    if not items:
        return fail("NO_DATA", f"'{keyword}' 결과가 없습니다.")
    return ok({"items": [{"id": it.get("id"), "name": it.get("name")}   # 판단에 쓸 값만
                         for it in items]})

# ── ④ 등록: 이름으로 찾는 Tool 목록 ──────────────────────────
TOOLS = {t.name: t for t in [
    Tool(name="search_items",
         description="TODO 언제 쓰는지 — 기능 이름이 아니라 '이럴 때 부른다'로 적는다.",
         parameters={"type": "object",
                     "properties": {"keyword": {"type": "string"}},
                     "required": ["keyword"]},
         func=search_items),
]}

def catalog():
    """Agent 에게 넘기는 것은 이름 · 설명 · 입력 규격뿐"""
    return [{"name": t.name, "description": t.description,
             "parameters": t.parameters} for t in TOOLS.values()]

if __name__ == "__main__":
    for c in catalog():                           # 등록한 목록 — Tool 정의서와 대조한다
        print("[Tool]", c["name"], "—", c["description"])
    tool = TOOLS["search_items"]

    def trial(name, **args):
        r = tool.run(**args)
        print(f"{r['ok']!s:<5} {name} →", r["data"] if r["ok"] else r["error"]["code"])

    trial("정상", keyword="테스트")               # TODO 결과가 나오는 검색어로
    trial("빈 입력", keyword="")
    key = os.environ.pop(KEY_NAME, "")           # 키 없음: 잠깐 비우고 부른다
    trial("키 없음", keyword="테스트")
    os.environ[KEY_NAME] = key
    trial("결과 없음", keyword="zzzzzz")          # TODO 결과가 없을 검색어로 (F3004)


