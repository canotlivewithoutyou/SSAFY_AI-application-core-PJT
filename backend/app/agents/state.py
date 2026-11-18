"""State contract to be used when the LangGraph dependency is connected."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypedDict


class PlannerRequest(TypedDict, total=False):
    origin_query: str
    origin_longitude: float
    origin_latitude: float
    institution_type: Literal["hospital", "pharmacy"]
    departure_at: datetime
    max_travel_seconds: int


class PlannerState(TypedDict, total=False):
    session_id: str
    user_message: str
    parsed_request: PlannerRequest
    candidates: list[dict[str, Any]]
    visited_institution_ids: list[str]
    replan_count: int
    selected_candidate: dict[str, Any]
    events: list[dict[str, Any]]
    final_answer: str
    error: str

