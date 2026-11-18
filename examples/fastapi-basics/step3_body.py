"""3단계 — 요청 본문과 Pydantic 모델

실행:
    uvicorn step3_body:app --reload

해 볼 것 (/docs 에서 POST /plans):
    정상        {"movie_nm": "명량", "watch_date": "2026-11-21"}
    필수 누락   movie_nm 을 빼고 보낸다      → 422, loc 에 "movie_nm"
    형식 틀림   "watch_date": "내일"         → 422
"""
from datetime import date

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class PlanIn(BaseModel):
    movie_nm: str
    watch_date: date #2026-11-18 날짜 형식만 통과, 내일, 모레
    start_time: str | None=None

@app.post("/plan")
def create_plan(plan: PlanIn):
    return {"saved": plan.model_dump()}