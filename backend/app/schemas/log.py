"""Read-only execution-log contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    request_id: str | None = None
    event_type: str
    stage: str
    payload: dict[str, Any]
    duration_ms: int | None
    created_at: datetime


class RequestRunOut(BaseModel):
    """One chat request inside a session, oldest first."""

    request_id: str | None
    event_count: int
    started_at: datetime
    ended_at: datetime
    duration_ms: int | None = None


class SessionTraceOut(BaseModel):
    """A session's events in execution order (id ASC).

    ``summary`` is filled only when ``request_id`` selects a single run.
    """

    session_id: str
    request_id: str | None = None
    latest_request_id: str | None = None
    requests: list[RequestRunOut] = Field(default_factory=list)
    events: list[ExecutionLogOut] = Field(default_factory=list)
    summary: dict[str, Any] | None = None
