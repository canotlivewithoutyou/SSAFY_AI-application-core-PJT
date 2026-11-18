"""5단계 — 관람 계획 CRUD (저장 · 목록 · 상세 · 수정 · 삭제)

실행:
    uvicorn step5_crud:app --reload

해 볼 것 (/docs 에서 한 바퀴):
"""
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class PlanIn(BaseModel):
    movie_nm: str
    watch_date: date
    start_time: str | None = None

class PlanOut(PlanIn):              
    plan_id: int

PLANS: dict[int, dict] = {}
NOT_FOUND = "그런 관람 계획이 없습니다."

@app.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(plan: PlanIn):
    pass

@app.get("/plans", response_model=list[PlanOut])
def list_plans():
    pass

@app.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int):
    pass

@app.put("/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, plan: PlanIn):      # 경로 + 본문
    pass

@app.delete("/plans/{plan_id}", status_code=204)  # 돌려줄 내용 없음
def delete_plan(plan_id: int):
    pass

