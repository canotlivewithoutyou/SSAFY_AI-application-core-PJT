"""Conversation entry point for deterministic help and the LangGraph planner."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..composition import get_event_bus, get_planner_agent
from ..config import Settings, settings_dependency
from ..schemas.chat import ChatRequest, ChatResponse
from ..services.chat import handle_chat


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: Settings = Depends(settings_dependency),
) -> ChatResponse:
    return handle_chat(
        request,
        settings,
        publisher=get_event_bus(settings),
        planner_factory=get_planner_agent,
    )
