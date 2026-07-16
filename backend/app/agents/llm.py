"""LLM boundary for structured request analysis and Tool-selection smoke tests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Mapping, Protocol

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ..config import Settings
from ..tools import ToolRegistry


class RequestAnalysis(BaseModel):
    intent: Literal["visit_plan", "help", "other"] = "visit_plan"
    origin_query: str | None = None
    institution_type: Literal["hospital", "pharmacy"] | None = None
    departure_at: str | None = Field(
        default=None,
        description="ISO 8601 with +09:00 offset; null when the user did not provide it",
    )
    max_travel_minutes: int | None = Field(default=None, ge=1, le=180)
    is_public_holiday: bool | None = None
    reason: str = Field(description="One concise sentence explaining the extraction")


class Analyzer(Protocol):
    def analyze(
        self,
        message: str,
        *,
        previous: Mapping[str, Any],
        now: datetime,
    ) -> dict[str, Any]: ...


class OpenAIAnalyzer:
    def __init__(self, settings: Settings, *, model: Any | None = None) -> None:
        self.settings = settings
        self.model = model or ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
            timeout=settings.upstream_timeout_seconds,
            max_retries=1,
        )

    def analyze(
        self,
        message: str,
        *,
        previous: Mapping[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        structured = self.model.with_structured_output(RequestAnalysis)
        prompt = (
            "You analyze a Korean hospital/pharmacy visit-planning request. "
            "Extract only values stated by the user; never invent a missing time, place, "
            "institution type, or travel limit. Preserve a prior value only when the latest "
            "message is a follow-up that changes another field. "
            f"Current Asia/Seoul datetime: {now.isoformat()}. "
            f"Prior context: {dict(previous)}. Latest message: {message}"
        )
        result = structured.invoke(prompt)
        if isinstance(result, BaseModel):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        raise TypeError("Structured LLM analysis returned an unsupported value")

    def probe(self, message: str, registry: ToolRegistry) -> dict[str, Any]:
        """Invoke the model with registered Tool schemas and expose only safe evidence."""

        bound = self.model.bind_tools(registry.llm_definitions(), tool_choice="auto")
        response = bound.invoke(message)
        tool_calls = []
        for call in getattr(response, "tool_calls", []) or []:
            tool_calls.append(
                {
                    "name": call.get("name"),
                    "args": call.get("args", {}),
                }
            )
        content = getattr(response, "content", "")
        if not isinstance(content, str):
            content = str(content)
        return {"answer": content, "tool_calls": tool_calls}
