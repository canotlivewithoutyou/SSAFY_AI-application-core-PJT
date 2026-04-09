"""Execution logs are list/detail/delete only; there is no public update API."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..config import Settings, settings_dependency
from ..repositories import logs as repository
from ..schemas.log import ExecutionLogOut, SessionTraceOut
from ..services.trace import summarize_request_events


router = APIRouter(prefix="/logs", tags=["logs"])
NOT_FOUND = "실행 로그를 찾을 수 없습니다."
SESSION_NOT_FOUND = "해당 세션의 실행 로그를 찾을 수 없습니다."


@router.get("", response_model=list[ExecutionLogOut])
async def list_logs(
    session_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    settings: Settings = Depends(settings_dependency),
    request_id: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> list[ExecutionLogOut]:
    """Newest first by default (backward compatible); ``order=asc`` for execution order."""

    events = repository.list_events(
        settings.database_path,
        session_id=session_id,
        request_id=request_id,
        limit=limit,
        order=order,
    )
    return [ExecutionLogOut.model_validate(event) for event in events]


@router.get("/sessions/{session_id}", response_model=SessionTraceOut)
async def get_session_logs(
    session_id: str,
    settings: Settings = Depends(settings_dependency),
    request_id: str | None = None,
    latest: bool = False,
) -> SessionTraceOut:
    """Return a session's full execution history in run order.

    ``request_id`` narrows the events to one chat request and adds a trace
    summary; ``latest=true`` does the same for the most recent request.
    """

    trace = repository.get_session_trace(settings.database_path, session_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
    selected = request_id or (trace["latest_request_id"] if latest else None)
    if selected:
        known = {item["request_id"] for item in trace["requests"]}
        if selected not in known:
            raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND)
        trace = repository.get_session_trace(
            settings.database_path, session_id, request_id=selected
        )
        trace["summary"] = summarize_request_events(trace["events"])
    return SessionTraceOut.model_validate(trace)


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
