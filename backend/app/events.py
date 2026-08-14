"""In-process execution event contract and publisher/subscriber bus (F3012).

The main Agent only knows :class:`EventPublisher`. Subscribers such as the
Logging Agent register themselves on an :class:`EventBus` at the composition
root, so a publisher never learns who (if anyone) receives its events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Mapping, Protocol


class EventType:
    """Canonical event names shared by publishers, subscribers and the UI."""

    REQUEST_RECEIVED = "request.received"
    REQUEST_COMPLETED = "request.completed"
    SETUP_REQUIRED = "setup.required"
    STAGE_ENTERED = "stage.entered"
    STAGE_EXITED = "stage.exited"
    ANALYSIS_COMPLETED = "analysis.completed"  # rule-based judgment and reason
    LLM_DECISION = "llm.decision"  # LLM-assisted judgment and reason
    PLAN_CREATED = "plan.created"
    TOOL_REQUESTED = "tool.requested"
    TOOL_RESPONDED = "tool.responded"  # carries duration_ms
    TOOL_CACHE_HIT = "tool.cache_hit"
    CANDIDATE_SELECTED = "candidate.selected"
    CANDIDATE_EXCLUDED = "candidate.excluded"
    PLAN_REPLANNED = "plan.replanned"
    RESPONSE_GENERATED = "response.generated"


SENSITIVE_FRAGMENTS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "secret",
    "service_key",
    "servicekey",
    "password",
)
REDACTED = "[REDACTED]"

# Values that look like credentials even when their key name is harmless.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(?:Bearer|KakaoAK|Basic)\s+[A-Za-z0-9_\-\.=+/]{6,}", re.IGNORECASE),
    re.compile(r"(?i)(service_?key|api_?key|token)=([^&\s]+)"),
)
# A single long opaque token (letters and digits mixed, no spaces).
_OPAQUE_TOKEN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_\-+/=%]{32,}$")


def _mask_text(value: str) -> str:
    if _OPAQUE_TOKEN.match(value):
        return REDACTED
    masked = value
    for pattern in _SECRET_VALUE_PATTERNS:
        masked = pattern.sub(REDACTED, masked)
    return masked


def sanitize_payload(value: Any) -> Any:
    """Redact secret-bearing keys and credential-like values recursively."""

    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            clean[str(key)] = (
                REDACTED
                if any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS)
                else sanitize_payload(item)
            )
        return clean
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return _mask_text(str(value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    session_id: str
    event_type: str
    stage: str
    request_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None
    created_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        event_type: str,
        stage: str,
        request_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        duration_ms: int | None = None,
    ) -> "ExecutionEvent":
        return cls(
            session_id=session_id,
            request_id=request_id,
            event_type=event_type,
            stage=stage,
            payload=sanitize_payload(payload or {}),
            duration_ms=duration_ms,
        )


class EventPublisher(Protocol):
    def publish(self, event: ExecutionEvent) -> None: ...


Subscriber = Callable[[ExecutionEvent], Any]


class EventBus:
    """Synchronous in-process fan-out that isolates subscriber failures."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = Lock()
        self.failed_deliveries = 0

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with self._lock:
                if subscriber in self._subscribers:
                    self._subscribers.remove(subscriber)

        return unsubscribe

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: ExecutionEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception:
                # A broken subscriber must never break the publishing Agent.
                self.failed_deliveries += 1
