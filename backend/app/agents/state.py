"""LangGraph state contract for the visit-planning Agent."""

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
    is_public_holiday: bool


class PlannerState(TypedDict, total=False):
    session_id: str
    user_message: str
    parsed_request: PlannerRequest
    analysis_source: str
    analysis_reason: str
    plan: list[str]
    missing_fields: list[str]
    candidates: list[dict[str, Any]]
    candidate_basis: str
    candidate_index: int
    current_candidate: dict[str, Any]
    current_detail: dict[str, Any]
    current_route: dict[str, Any]
    visited_institution_ids: list[str]
    replan_count: int
    needs_replan: bool
    exclusions: list[dict[str, Any]]
    selected_candidate: dict[str, Any]
    tool_cache: dict[str, dict[str, Any]]
    tool_calls: list[str]
    events: list[dict[str, Any]]
    clarification: str
    stop_reason: str
    final_answer: str
    error: str

