"""Temporary deterministic chat behavior used before the Agent is connected."""

from __future__ import annotations

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
    return ChatResponse(
        session_id=request.session_id,
        status="setup_required",
        answer=(
            "프로젝트 기초 구조는 준비됐지만 추천 Agent와 외부 API는 아직 연결 전입니다. "
            "환경변수와 실제 Tool 구현을 연결한 뒤 이 요청을 처리할 수 있습니다."
        ),
        missing_settings=missing,
        tool_calls=[],
    )

