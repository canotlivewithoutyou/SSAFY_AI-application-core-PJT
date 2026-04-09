"""Turn one request's stored events into a display-ready execution trace (F3019).

The summary is derived only from events that the Logging Agent actually
stored, so the UI never shows a stage or Tool that did not run.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..events import EventType


def summarize_request_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize events that belong to a single request, in id ASC order."""

    ordered = sorted(events, key=lambda event: event.get("id") or 0)
    stages: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    pending_tools: dict[str, dict[str, Any]] = {}
    status: str | None = None
    decision: dict[str, Any] | None = None
    missing_settings: list[str] = []
    replan_count = 0
    excluded_count = 0
    selected: dict[str, Any] | None = None
    stop_reason: str | None = None

    for event in ordered:
        kind = event.get("event_type")
        payload = event.get("payload") or {}
        base = {"event_id": event.get("id"), "stage": event.get("stage")}

        if kind == EventType.STAGE_EXITED:
            stages.append(
                {
                    "stage": event.get("stage"),
                    "status": payload.get("status") or "completed",
                    "duration_ms": event.get("duration_ms"),
                }
            )
        elif kind in (EventType.ANALYSIS_COMPLETED, EventType.LLM_DECISION):
            decision = {
                "decision_maker": payload.get("decision_maker")
                or ("llm" if kind == EventType.LLM_DECISION else "rules"),
                "source": payload.get("source"),
                "reason": payload.get("reason"),
            }
            timeline.append({**base, "kind": "decision", **decision})
        elif kind == EventType.TOOL_REQUESTED:
            pending_tools[str(payload.get("tool"))] = {
                "tool": payload.get("tool"),
                "attempt": payload.get("attempt", 0),
            }
        elif kind == EventType.TOOL_RESPONDED:
            name = str(payload.get("tool"))
            call = {
                "order": len(tools) + 1,
                "tool": payload.get("tool"),
                "cached": False,
                "ok": bool(payload.get("ok")),
                "error_code": payload.get("error_code"),
                "error_message": payload.get("error_message"),
                "duration_ms": event.get("duration_ms"),
                "attempt": payload.get("attempt", pending_tools.pop(name, {}).get("attempt", 0)),
            }
            tools.append(call)
            timeline.append({**base, "kind": "tool", **call})
        elif kind == EventType.TOOL_CACHE_HIT:
            call = {
                "order": len(tools) + 1,
                "tool": payload.get("tool"),
                "cached": True,
                "ok": bool(payload.get("ok", True)),
                "error_code": None,
                "error_message": None,
                "duration_ms": None,
                "attempt": payload.get("attempt", 0),
            }
            tools.append(call)
            timeline.append({**base, "kind": "tool", **call})
        elif kind == EventType.CANDIDATE_EXCLUDED:
            excluded_count += 1
            timeline.append(
                {
                    **base,
                    "kind": "candidate_excluded",
                    "institution_id": payload.get("institution_id"),
                    "name": payload.get("name"),
                    "code": payload.get("code"),
                    "reason": payload.get("reason"),
                    "will_replan": bool(payload.get("will_replan")),
                    "stop_reason": payload.get("stop_reason"),
                }
            )
            if payload.get("stop_reason"):
                stop_reason = payload.get("stop_reason")
        elif kind == EventType.CANDIDATE_SELECTED:
            selected = {
                "institution_id": payload.get("institution_id"),
                "name": payload.get("name"),
                "code": payload.get("code"),
                "reason": payload.get("reason"),
            }
            timeline.append({**base, "kind": "candidate_selected", **selected})
        elif kind == EventType.PLAN_REPLANNED:
            replan_count = max(replan_count, int(payload.get("replan_count") or 0))
            timeline.append(
                {
                    **base,
                    "kind": "replan",
                    "replan_count": payload.get("replan_count"),
                    "limit": payload.get("limit"),
                    "reason": payload.get("reason"),
                }
            )
        elif kind == EventType.SETUP_REQUIRED:
            missing_settings = [str(name) for name in payload.get("missing_settings") or []]
            timeline.append({**base, "kind": "setup_required", "missing_settings": missing_settings})
        elif kind == EventType.RESPONSE_GENERATED:
            stop_reason = payload.get("stop_reason") or stop_reason
        elif kind == EventType.REQUEST_COMPLETED:
            status = payload.get("status")

    failed_tools = [call for call in tools if not call["ok"]]
    return {
        "status": status,
        "completed": status is not None,
        "decision": decision,
        "stages": stages,
        "tools": tools,
        "timeline": timeline,
        "tool_call_count": sum(1 for call in tools if not call["cached"]),
        "cache_hit_count": sum(1 for call in tools if call["cached"]),
        "failed_tool_count": len(failed_tools),
        "replan_count": replan_count,
        "excluded_count": excluded_count,
        "selected": selected,
        "stop_reason": stop_reason,
        "missing_settings": missing_settings,
    }
