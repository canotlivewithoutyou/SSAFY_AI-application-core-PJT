"""Conversation service that routes help locally and planning to LangGraph."""

from __future__ import annotations

from ..agents.planner import get_planner_agent
from ..config import Settings
from ..schemas.chat import ChatRequest, ChatResponse


HELP_PHRASES = ("어떻게 써", "사용법", "도움말", "how to use")
USAGE_MESSAGE = (
    "출발지, 병원 또는 약국, 출발 날짜·시각, 허용 이동시간을 알려 주세요. "
    "예: ‘성남 판교역 신분당선에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘.’ "
    "공개 운영시간과 예상 이동시간을 바탕으로 안내하며, 실제 운영·접수 여부는 방문 전에 기관에 확인해야 합니다."
)


def handle_chat(request: ChatRequest, settings: Settings) -> ChatResponse:
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

    try:
        outcome = get_planner_agent(settings).run(
            session_id=request.session_id,
            message=request.message,
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
        excluded_candidates=list(outcome.get("exclusions") or []),
        replan_count=int(outcome.get("replan_count") or 0),
    )
