"""Conversation service that routes help locally and planning to LangGraph."""

from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any, Callable, Mapping
from uuid import uuid4

from pydantic import ValidationError

from ..composition import get_planner_agent
from ..config import Settings
from ..events import EventBus, EventPublisher, EventType, ExecutionEvent
from ..schemas.chat import ChatRequest, ChatResponse
from ..schemas.plan import PlanCreate


HELP_PHRASES = ("어떻게 써", "사용법", "도움말", "how to use")
USAGE_MESSAGE = (
    "출발지, 병원 또는 약국, 출발 날짜·시각, 허용 이동시간을 알려 주세요. "
    "예: ‘성남 판교역 신분당선에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘.’ "
    "공개 운영시간과 예상 이동시간을 바탕으로 안내하며, 실제 운영·접수 여부는 방문 전에 기관에 확인해야 합니다."
)


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def build_plan_draft(outcome: Mapping[str, Any]) -> PlanCreate | None:
    """Convert a successful recommendation into the exact plan-create contract."""

    request = outcome.get("parsed_request") or {}
    recommendation = outcome.get("selected_candidate") or {}
    departure = _datetime(request.get("departure_at"))
    arrival = _datetime(recommendation.get("expected_arrival_at"))
    if departure is None or arrival is None or not recommendation:
        return None

    interval: Mapping[str, Any] | None = None
    for candidate_interval in recommendation.get("opening_intervals") or []:
        start = _datetime(candidate_interval.get("start"))
        end = _datetime(candidate_interval.get("end"))
        if start is not None and end is not None and start <= arrival < end:
            interval = candidate_interval
            break

    try:
        return PlanCreate.model_validate(
            {
                "institution_type": request.get("institution_type"),
                "institution_id": recommendation.get("institution_id"),
                "institution_name": recommendation.get("name"),
                "institution_address": recommendation.get("address"),
                "visit_date": arrival.date(),
                "origin_name": request.get("origin_name") or request.get("origin_query"),
                "origin_longitude": request.get("origin_longitude"),
                "origin_latitude": request.get("origin_latitude"),
                "destination_longitude": recommendation.get("longitude"),
                "destination_latitude": recommendation.get("latitude"),
                "departure_at": departure,
                "expected_arrival_at": arrival,
                "travel_duration_seconds": recommendation.get("duration_seconds"),
                "operation_start": interval.get("start") if interval else None,
                "operation_end": interval.get("end") if interval else None,
                "selection_reason": recommendation.get("selection_reason"),
            }
        )
    except (TypeError, ValidationError):
        return None


def _publish(
    publisher: EventPublisher,
    request: ChatRequest,
    request_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    duration_ms: int | None = None,
) -> None:
    try:
        publisher.publish(
            ExecutionEvent.create(
                session_id=request.session_id,
                request_id=request_id,
                event_type=event_type,
                stage="chat",
                payload=payload,
                duration_ms=duration_ms,
            )
        )
    except Exception:
        return


def handle_chat(
    request: ChatRequest,
    settings: Settings,
    *,
    publisher: EventPublisher | None = None,
    planner_factory: Callable[[Settings], Any] | None = None,
    request_id: str | None = None,
) -> ChatResponse:
    """Run one chat request and publish its start/finish events.

    The response carries ``request_id`` so a client can fetch exactly this
    run's trace from ``GET /logs/sessions/{session_id}?request_id=...``.
    """

    publisher = publisher or EventBus()
    request_id = request_id or uuid4().hex
    _publish(
        publisher,
        request,
        request_id,
        EventType.REQUEST_RECEIVED,
        {"message_length": len(request.message)},
    )
    started = perf_counter()
    response = _handle(request, settings, request_id, publisher, planner_factory)
    response.request_id = request_id
    _publish(
        publisher,
        request,
        request_id,
        EventType.REQUEST_COMPLETED,
        {
            "status": response.status,
            "tool_calls": response.tool_calls,
            "tool_call_count": len(response.tool_calls),
            "replan_count": response.replan_count,
        },
        duration_ms=int((perf_counter() - started) * 1000),
    )
    return response


def _handle(
    request: ChatRequest,
    settings: Settings,
    request_id: str,
    publisher: EventPublisher,
    planner_factory: Callable[[Settings], Any] | None,
) -> ChatResponse:
    normalized = request.message.casefold()
    if any(phrase in normalized for phrase in HELP_PHRASES):
        return ChatResponse(
            session_id=request.session_id,
            status="completed",
            answer=USAGE_MESSAGE,
            tool_calls=[],
        )

    missing = settings.missing_integration_settings()
    if missing:
        # Only variable names are published; values are never read here.
        _publish(
            publisher,
            request,
            request_id,
            EventType.SETUP_REQUIRED,
            {"missing_settings": missing},
        )
        return ChatResponse(
            session_id=request.session_id,
            status="setup_required",
            answer=(
                "추천 Agent 실행에 필요한 환경변수가 아직 설정되지 않았습니다. "
                "키 값은 .env에만 넣고 서버를 다시 시작해 주세요."
            ),
            missing_settings=missing,
            tool_calls=[],
        )

    if planner_factory is None:
        planner_factory = get_planner_agent

    try:
        outcome = planner_factory(settings).run(
            session_id=request.session_id,
            message=request.message,
            request_id=request_id,
        )
    except Exception:
        return ChatResponse(
            session_id=request.session_id,
            status="failed",
            answer="요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )

    if outcome.get("clarification"):
        status = "needs_input"
    elif outcome.get("selected_candidate"):
        status = "completed"
    else:
        status = "failed"
    return ChatResponse(
        session_id=request.session_id,
        status=status,
        answer=str(outcome.get("final_answer") or "응답을 생성하지 못했습니다."),
        tool_calls=list(outcome.get("tool_calls") or []),
        request_context=dict(outcome.get("parsed_request") or {}),
        recommendation=dict(outcome.get("selected_candidate") or {}) or None,
        plan_draft=build_plan_draft(outcome),
        excluded_candidates=list(outcome.get("exclusions") or []),
        replan_count=int(outcome.get("replan_count") or 0),
    )
