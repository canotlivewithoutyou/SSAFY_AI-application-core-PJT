"""Logging Agent: a non-LLM event subscriber that persists events to SQLite (F3013).

It is registered on an :class:`~backend.app.events.EventBus` by the
composition root. Publishers never import this module, and a storage failure
here is isolated by the bus so it cannot block the main planner response.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..events import EventBus, ExecutionEvent
from ..repositories.logs import record_event


class LoggingAgent:
    """Stores every received event. It never calls an LLM or an external API."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def __call__(self, event: ExecutionEvent) -> None:
        self.handle(event)

    def handle(self, event: ExecutionEvent) -> None:
        record_event(
            self.database_path,
            session_id=event.session_id,
            request_id=event.request_id,
            event_type=event.event_type,
            stage=event.stage,
            payload=event.payload,
            duration_ms=event.duration_ms,
            created_at=event.created_at,
        )


def subscribe_logging_agent(bus: EventBus, database_path: Path) -> Callable[[], None]:
    """Register a Logging Agent on ``bus`` and return its unsubscribe handle."""

    return bus.subscribe(LoggingAgent(database_path))
