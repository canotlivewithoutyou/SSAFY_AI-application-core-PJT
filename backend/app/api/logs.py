"""Execution logs are list/detail/delete only; there is no public update API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..config import Settings, settings_dependency
from ..repositories import logs as repository
from ..schemas.log import ExecutionLogOut


router = APIRouter(prefix="/logs", tags=["logs"])
NOT_FOUND = "실행 로그를 찾을 수 없습니다."


@router.get("", response_model=list[ExecutionLogOut])
async def list_logs(
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    settings: Settings = Depends(settings_dependency),
) -> list[ExecutionLogOut]:
    events = repository.list_events(
        settings.database_path, session_id=session_id, limit=limit
    )
    return [ExecutionLogOut.model_validate(event) for event in events]


@router.get("/{event_id}", response_model=ExecutionLogOut)
async def get_log(
    event_id: int,
    settings: Settings = Depends(settings_dependency),
) -> ExecutionLogOut:
    event = repository.get_event(settings.database_path, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return ExecutionLogOut.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(
    event_id: int,
    settings: Settings = Depends(settings_dependency),
) -> Response:
    if not repository.delete_event(settings.database_path, event_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

