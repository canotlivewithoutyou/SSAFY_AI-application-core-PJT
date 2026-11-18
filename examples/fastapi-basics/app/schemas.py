"""요청 · 응답 형식. 라우터가 가져다 쓴다.
"""
from datetime import date

from pydantic import BaseModel

class PlanIn(BaseModel):
    movie_nm: str
    watch_date: date
    start_time: str | None = None

class PlanOut(PlanIn):
    plan_id: int
