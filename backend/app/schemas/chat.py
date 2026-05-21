"""Conversation endpoint contracts."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .plan import PlanCreate


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    session_id: str
    status: Literal["completed", "needs_input", "setup_required", "failed"]
    answer: str
    missing_settings: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    request_context: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] | None = None
    plan_draft: PlanCreate | None = None
    excluded_candidates: list[dict[str, Any]] = Field(default_factory=list)
    replan_count: int = 0

