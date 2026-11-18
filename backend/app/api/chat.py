"""Conversation entry point.

The deterministic help response works now. Recommendation requests explicitly
report setup_required until the real Agent and Tool handlers are connected.
"""

from __future__ import annotations

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
    response = handle_chat(request, settings)
    emit_safely(
        settings.database_path,
        session_id=request.session_id,
        event_type="request.completed",
        stage="chat",
        payload={"status": response.status, "tool_calls": response.tool_calls},
    )
    return response

