"""관람 계획 라우터

prefix 덕분에 경로 앞부분(/api/plans)을 한 번만 적는다.
5단계 step5_crud.py 의 함수를 그대로 옮기고 @app → @router 로 바꿨다.
"""
from fastapi import APIRouter, HTTPException

from ..schemas import PlanIn, PlanOut
from ..store import PLANS

router = APIRouter(prefix="/api/plans", tags=["plans"])
NOT_FOUND = "그런 관람 계획이 없습니다."

@router.post("", response_model=PlanOut, status_code=201)
def create_plan(plan: PlanIn):
    plan_id = max(PLANS, default=0) + 1
    PLANS[plan_id] = {"plan_id": plan_id, **plan.model_dump()}
    return PLANS[plan_id]

@router.get("", response_model=list[PlanOut])    # 실제 주소는 /api/plans
def list_plans():
    return list(PLANS.values())

@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int):
    if plan_id not in PLANS:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return PLANS[plan_id]

@router.put("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, plan: PlanIn):
    if plan_id not in PLANS:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    PLANS[plan_id].update(plan.model_dump())
    return PLANS[plan_id]

@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int):
    if PLANS.pop(plan_id, None) is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
