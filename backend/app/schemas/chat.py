"""Conversation endpoint contracts."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    session_id: str
    status: Literal["completed", "setup_required"]
    answer: str
    missing_settings: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)

