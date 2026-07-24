r"""Run the replan-limit scenario with REPLAN_LIMIT forced to 1.

The chat service, LangGraph planner, real Tools and the Logging Agent run
in-process, so the result does not depend on a running server or on
environment variables left in a terminal.

Usage from the repository root::

    .\.venv\Scripts\python.exe -m backend.scripts.run_replan_limit_scenario

The evidence JSON is written to ``docs/evidence/scenario-replan-limit.json``.
API keys and raw upstream payloads are never printed or saved.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

# Captured before the config module loads .env, to show what the parent
# process (terminal or Explorer) passed down.
_INHERITED_REPLAN_LIMIT = os.environ.get("REPLAN_LIMIT")

from dotenv import dotenv_values  # noqa: E402

from backend.app.agents.parsing import SEOUL  # noqa: E402
from backend.app.agents.planner import PlannerAgent  # noqa: E402
from backend.app.composition import get_event_bus  # noqa: E402
from backend.app.config import PROJECT_ROOT, Settings, get_settings  # noqa: E402
from backend.app.database import initialize_database  # noqa: E402
from backend.app.events import EventType  # noqa: E402
from backend.app.repositories.logs import get_session_trace  # noqa: E402
from backend.app.schemas.chat import ChatRequest  # noqa: E402
from backend.app.services.chat import handle_chat  # noqa: E402
from backend.app.services.trace import summarize_request_events  # noqa: E402


MESSAGE = "성남 판교역 신분당선에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘"
REPLAN_LIMIT = 1
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "evidence" / "scenario-replan-limit.json"


def run(
    *,
    base_settings: Settings | None = None,
    registry: Any | None = None,
    analyzer: Any | None = None,
    session_id: str | None = None,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    base = base_settings or get_settings()
    settings = replace(base, replan_limit=REPLAN_LIMIT)
    initialize_database(settings.database_path)
    bus = get_event_bus(settings)
    agent = PlannerAgent(settings, registry=registry, analyzer=analyzer, publisher=bus)
    session_id = session_id or f"scenario-limit-{datetime.now(SEOUL):%H%M%S}"

    response = handle_chat(
        ChatRequest(session_id=session_id, message=MESSAGE),
        settings,
        publisher=bus,
        planner_factory=lambda _: agent,
    )
    trace = get_session_trace(
        settings.database_path, session_id, request_id=response.request_id
    )
    trace["summary"] = summarize_request_events(trace["events"])

    evidence = {
        "scenario": "replan_limit",
        "executed_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "configured_replan_limit": REPLAN_LIMIT,
        "environment_check": {
            "inherited_REPLAN_LIMIT_before_dotenv": _INHERITED_REPLAN_LIMIT,
            "dotenv_REPLAN_LIMIT": dotenv_values(PROJECT_ROOT / ".env").get("REPLAN_LIMIT"),
            "settings_REPLAN_LIMIT_without_override": base.replan_limit,
        },
        "chat_response": response.model_dump(mode="json"),
        "trace": trace,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return evidence


def main() -> int:
    settings = get_settings()
    missing = settings.missing_integration_settings()
    if missing:
        print("필요한 환경변수가 없습니다:", ", ".join(missing))
        return 1

    evidence = run()
    response = evidence["chat_response"]
    summary = evidence["trace"]["summary"]
    limits = sorted(
        {
            event["payload"].get("limit")
            for event in evidence["trace"]["events"]
            if event["event_type"] == EventType.PLAN_REPLANNED
        }
    )
    check = evidence["environment_check"]
    print("=== 재계획 상한 시나리오 ===")
    print("session_id     :", response["session_id"])
    print("request_id     :", response["request_id"])
    print("status         :", response["status"])
    print("replan_count   :", response["replan_count"])
    print("기록된 limit   :", limits)
    print("stop_reason    :", summary.get("stop_reason"))
    print("제외 후보      :", [item.get("name") for item in response["excluded_candidates"]])
    print("응답시간(ms)   :", evidence["trace"]["requests"][-1]["duration_ms"])
    print()
    print("=== 환경 확인 ===")
    print("상위 프로세스에서 물려받은 REPLAN_LIMIT:", check["inherited_REPLAN_LIMIT_before_dotenv"])
    print(".env의 REPLAN_LIMIT                    :", check["dotenv_REPLAN_LIMIT"])
    print()
    passed = (
        response["status"] == "failed"
        and limits == [REPLAN_LIMIT]
        and "재계획 상한" in (summary.get("stop_reason") or "")
    )
    print("판정:", "통과" if passed else "확인 필요")
    print("저장 위치:", DEFAULT_OUTPUT)
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
