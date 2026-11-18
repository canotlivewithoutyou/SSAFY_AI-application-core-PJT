"""4단계 — 응답 모델과 상태 코드

실행:
    uvicorn step4_response:app --reload

해 볼 것:
    start_time 을 넣어 저장한다 → 응답에는 없다. response_model 이 걸러 낸 것이다
    저장에 성공하면 200 이 아니라 201 이 온다
    서버를 다시 켜면 PLANS 가 빈다 (지금은 메모리)
"""
from datetime import date

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class PlanIn(BaseModel):
    movie_nm: str
    watch_date: date #2026-11-18 날짜 형식만 통과, 내일, 모레
    start_time: str | None=None

class PlanOut(BaseModel):
    plan_id: int
    movie_name: str
    watch_date: date

PLANS: dict[int, dict] = {}


@app.post("/plan", response_model=PlanOut, status_code=201)
def create_plan(plan: PlanIn):
    plan_id = max(PLANS, default=0) + 1
    PLANS[plan_id] = {"plan_id": plan_id, **plan.model_dump()}
    return PLANS[plan_id]



