r"""Measure NF3005 response time for the representative request.

Runs the chat service in-process ``RUNS`` times, each in a fresh session so no
cache is reused, then reports p50/p95/max of ``request.completed.duration_ms``.

Usage from the repository root::

    .\.venv\Scripts\python.exe -m backend.scripts.measure_response_time

The result is written to ``docs/evidence/perf-response-time.json``.
API keys and raw upstream payloads are never printed or saved.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.agents.parsing import SEOUL
from backend.app.composition import get_event_bus, get_planner_agent
from backend.app.config import PROJECT_ROOT, get_settings
from backend.app.database import initialize_database
from backend.app.events import EventType
from backend.app.repositories.logs import get_session_trace
from backend.app.schemas.chat import ChatRequest
from backend.app.services.chat import handle_chat


MESSAGE = "성남 판교역 신분당선에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘"
RUNS = 20
TARGET_P95_MS = 10_000
OUTPUT = PROJECT_ROOT / "docs" / "evidence" / "perf-response-time.json"


def percentile(values: list[int], ratio: float) -> int:
    """Nearest-rank percentile: the smallest value covering ``ratio`` of samples."""

    ordered = sorted(values)
    rank = max(1, math.ceil(ratio * len(ordered)))
    return ordered[rank - 1]


def _stage_ms(events: list[dict[str, Any]], stage: str) -> int:
    return sum(
        event["duration_ms"] or 0
        for event in events
        if event["event_type"] == EventType.STAGE_EXITED and event["stage"] == stage
    )


def run(runs: int = RUNS, *, settings=None, planner_factory=None, output_path: Path = OUTPUT) -> dict[str, Any]:
    settings = settings or get_settings()
    initialize_database(settings.database_path)
    bus = get_event_bus(settings)
    factory = planner_factory or get_planner_agent
    stamp = datetime.now(SEOUL).strftime("%H%M%S")
    samples: list[dict[str, Any]] = []

    for index in range(1, runs + 1):
        session_id = f"perf-{stamp}-{index:02d}"
        response = handle_chat(
            ChatRequest(session_id=session_id, message=MESSAGE),
            settings,
            publisher=bus,
            planner_factory=factory,
        )
        trace = get_session_trace(
            settings.database_path, session_id, request_id=response.request_id
        )
        events = trace["events"] if trace else []
        completed = [e for e in events if e["event_type"] == EventType.REQUEST_COMPLETED]
        decision = next(
            (
                e["payload"].get("source")
                for e in events
                if e["event_type"] in (EventType.LLM_DECISION, EventType.ANALYSIS_COMPLETED)
            ),
            None,
        )
        samples.append(
            {
                "run": index,
                "session_id": session_id,
                "request_id": response.request_id,
                "status": response.status,
                "total_ms": completed[-1]["duration_ms"] if completed else None,
                "analysis_ms": _stage_ms(events, "analyze_request"),
                "tool_ms": sum(
                    e["duration_ms"] or 0
                    for e in events
                    if e["event_type"] == EventType.TOOL_RESPONDED
                ),
                "tool_calls": len(response.tool_calls),
                "replan_count": response.replan_count,
                "analysis_source": decision,
            }
        )
        print(f"[{index:02d}/{runs}] {response.status} {samples[-1]['total_ms']}ms")

    totals = [s["total_ms"] for s in samples if s["total_ms"] is not None]
    summary = {
        "runs": len(totals),
        "p50_ms": percentile(totals, 0.50) if totals else None,
        "p95_ms": percentile(totals, 0.95) if totals else None,
        "max_ms": max(totals) if totals else None,
        "min_ms": min(totals) if totals else None,
        "mean_ms": round(statistics.fmean(totals)) if totals else None,
        "analysis_p50_ms": percentile([s["analysis_ms"] for s in samples], 0.50) if samples else None,
        "tool_p50_ms": percentile([s["tool_ms"] for s in samples], 0.50) if samples else None,
        "target": f"p95 <= {TARGET_P95_MS}ms",
        "all_completed": all(s["status"] == "completed" for s in samples),
        "all_used_llm": all((s["analysis_source"] or "").startswith("llm") for s in samples),
    }
    summary["passed"] = bool(totals) and summary["p95_ms"] <= TARGET_P95_MS
    result = {
        "measured_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "message": MESSAGE,
        "method": "in-process chat service, fresh session per run, request.completed.duration_ms, nearest-rank percentile",
        "summary": summary,
        "samples": samples,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    settings = get_settings()
    missing = settings.missing_integration_settings()
    if missing:
        print("필요한 환경변수가 없습니다:", ", ".join(missing))
        return 1
    print(f"정상 추천 요청을 {RUNS}회 실행합니다. 2~3분 걸립니다.")
    result = run()
    s = result["summary"]
    print()
    print("=== NF3005 응답시간 ===")
    print(f"p50 {s['p50_ms']}ms / p95 {s['p95_ms']}ms / 최대 {s['max_ms']}ms / 최소 {s['min_ms']}ms")
    print(f"LLM 분석 p50 {s['analysis_p50_ms']}ms / Tool 합계 p50 {s['tool_p50_ms']}ms")
    print("모든 요청 completed:", s["all_completed"], "/ 모든 요청 LLM 분석:", s["all_used_llm"])
    print("판정 (p95 10초 이내):", "통과" if s["passed"] else "미달")
    print("저장 위치:", OUTPUT)
    return 0 if s["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
