"""Non-LLM event sink that cannot block the main planner response."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..repositories.logs import record_event


def emit_safely(
    database_path: Path,
    *,
    session_id: str,
    event_type: str,
    stage: str,
    payload: Mapping[str, Any] | None = None,
    duration_ms: int | None = None,
) -> bool:
    try:
        record_event(
            database_path,
            session_id=session_id,
            event_type=event_type,
            stage=stage,
            payload=payload,
            duration_ms=duration_ms,
        )
    except Exception:
        return False
    return True

