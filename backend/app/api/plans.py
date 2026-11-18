"""Persistent visit-plan CRUD endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..config import Settings, settings_dependency
from ..repositories import plans as repository
from ..schemas.plan import PlanCreate, PlanMutationResponse, PlanOut, PlanUpdate


router = APIRouter(prefix="/plans", tags=["plans"])
NOT_FOUND = "방문 계획을 찾을 수 없습니다."


def _mutation_result(settings: Settings, plan: PlanOut) -> PlanMutationResponse:
    overlapping_ids = repository.find_overlapping_plan_ids(
        settings.database_path,
        visit_date=plan.visit_date,
        departure_at=plan.departure_at,
        expected_arrival_at=plan.expected_arrival_at,
        exclude_plan_id=plan.id,
    )
    warnings = (
        ["같은 날짜에 시간이 겹치는 방문 계획이 있습니다."]
        if overlapping_ids
        else []
    )
    return PlanMutationResponse(
        plan=plan,
        warnings=warnings,
        overlapping_plan_ids=overlapping_ids,
    )


@router.post("", response_model=PlanMutationResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreate,
    settings: Settings = Depends(settings_dependency),
) -> PlanMutationResponse:
    item = repository.create_plan(settings.database_path, payload.model_dump())
    return _mutation_result(settings, PlanOut.model_validate(item))


@router.get("", response_model=list[PlanOut])
async def list_plans(
    visit_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    settings: Settings = Depends(settings_dependency),
) -> list[PlanOut]:
    items = repository.list_plans(
        settings.database_path, visit_date=visit_date, limit=limit
    )
    return [PlanOut.model_validate(item) for item in items]


@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: int,
    settings: Settings = Depends(settings_dependency),
) -> PlanOut:
    item = repository.get_plan(settings.database_path, plan_id)
    if item is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return PlanOut.model_validate(item)


@router.patch("/{plan_id}", response_model=PlanMutationResponse)
async def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    settings: Settings = Depends(settings_dependency),
) -> PlanMutationResponse:
    current = repository.get_plan(settings.database_path, plan_id)
    if current is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    requested_changes = payload.model_dump(exclude_unset=True)
    if not requested_changes:
        raise HTTPException(status_code=400, detail="변경할 값을 한 개 이상 보내 주세요.")

    validated = PlanCreate.model_validate({**current, **requested_changes})
    normalized = validated.model_dump()
    changes = {field: normalized[field] for field in requested_changes}
    item = repository.update_plan(settings.database_path, plan_id, changes)
    if item is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return _mutation_result(settings, PlanOut.model_validate(item))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: int,
    settings: Settings = Depends(settings_dependency),
) -> Response:
    if not repository.delete_plan(settings.database_path, plan_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

