"""Read-only execution-log contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ExecutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    event_type: str
    stage: str
    payload: dict[str, Any]
    duration_ms: int | None
    created_at: datetime

