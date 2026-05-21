"""Conversation entry point for deterministic help and the LangGraph planner."""

from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Depends

from ..agents.logging_agent import emit_safely
from ..config import Settings, settings_dependency
from ..schemas.chat import ChatRequest, ChatResponse
from ..services.chat import handle_chat


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: Settings = Depends(settings_dependency),
) -> ChatResponse:
    emit_safely(
        settings.database_path,
        session_id=request.session_id,
        event_type="request.received",
        stage="chat",
        payload={"message_length": len(request.message)},
    )
    started = perf_counter()
    response = handle_chat(request, settings)
    emit_safely(
        settings.database_path,
        session_id=request.session_id,
        event_type="request.completed",
        stage="chat",
        payload={"status": response.status, "tool_calls": response.tool_calls},
        duration_ms=int((perf_counter() - started) * 1000),
    )
    return response

