"""LangGraph execution flow for F3005-F3011."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import wraps
from time import perf_counter
from uuid import uuid4
from typing import Any, Callable, Mapping

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..config import Settings
from ..events import EventBus, EventPublisher, EventType, ExecutionEvent
from ..services.availability import OpeningInterval, evaluate_visit
from ..tools import ToolRegistry, ToolResult, build_registry
from .llm import Analyzer, OpenAIAnalyzer
from .parsing import SEOUL, extract_explicit_fields, normalize_llm_fields
from .state import PlannerState


MEDICAL_NOTICE = (
    "공개 운영시간과 예상 이동시간을 바탕으로 한 방문 안내입니다. "
    "실제 운영 및 접수 여부는 방문 전 기관에 확인해 주세요. "
    "이 서비스는 전문가의 의료 상담을 대신하지 않습니다."
)

MISSING_LABELS = {
    "origin": "출발지",
    "institution_type": "기관 종류(병원 또는 약국)",
    "departure_at": "출발 날짜와 시각",
    "max_travel_seconds": "최대 이동시간",
}


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(SEOUL) if value.tzinfo else value.replace(tzinfo=SEOUL)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(SEOUL) if parsed.tzinfo else parsed.replace(tzinfo=SEOUL)
    return None


def _cache_key(name: str, arguments: Mapping[str, Any]) -> str:
    return json.dumps(
        {"name": name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        separators=(",", ":"),
    )


def _candidate_basis(request: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "longitude": request.get("origin_longitude"),
            "latitude": request.get("origin_latitude"),
            "institution_type": request.get("institution_type"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _missing_fields(request: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if not (
        request.get("origin_query")
        or (
            request.get("origin_longitude") is not None
            and request.get("origin_latitude") is not None
        )
    ):
        missing.append("origin")
    for field in ("institution_type", "departure_at", "max_travel_seconds"):
        if request.get(field) is None:
            missing.append(field)
    return missing


def _format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "확인 불가"
    minutes, remainder = divmod(max(0, seconds), 60)
    if minutes and remainder:
        return f"{minutes}분 {remainder}초"
    if minutes:
        return f"{minutes}분"
    return f"{remainder}초"


def _format_datetime(value: Any) -> str:
    parsed = _datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else "확인 불가"


class PlannerAgent:
    def __init__(
        self,
        settings: Settings,
        *,
        registry: ToolRegistry | None = None,
        analyzer: Analyzer | None = None,
        checkpointer: InMemorySaver | None = None,
        now: Any | None = None,
        publisher: EventPublisher | None = None,
    ) -> None:
        self.settings = settings
        # The planner only publishes. Without an injected publisher it uses a
        # bus with no subscribers, so it never depends on a storage backend.
        self.publisher: EventPublisher = publisher or EventBus()
        self.registry = registry or build_registry(settings)
        self.now = now or (lambda: datetime.now(SEOUL))
        self.analyzer = analyzer
        if self.analyzer is None and settings.openai_api_key and settings.openai_model:
            self.analyzer = OpenAIAnalyzer(settings)

        graph = StateGraph(PlannerState)
        graph.add_node(
            "analyze_request",
            self._stage_node("analyze_request", self._analyze_request),
        )
        graph.add_node("build_plan", self._stage_node("build_plan", self._build_plan))
        graph.add_node(
            "execute_tools",
            self._stage_node("execute_tools", self._execute_tools),
        )
        graph.add_node(
            "judge_constraints",
            self._stage_node("judge_constraints", self._judge_constraints),
        )
        graph.add_node("replan", self._stage_node("replan", self._replan))
        graph.add_node(
            "generate_response",
            self._stage_node("generate_response", self._generate_response),
        )
        graph.add_edge(START, "analyze_request")
        graph.add_edge("analyze_request", "build_plan")
        graph.add_edge("build_plan", "execute_tools")
        graph.add_edge("execute_tools", "judge_constraints")
        graph.add_conditional_edges(
            "judge_constraints",
            self._after_judgment,
            {"replan": "replan", "respond": "generate_response"},
        )
        graph.add_edge("replan", "execute_tools")
        graph.add_edge("generate_response", END)
        self.graph = graph.compile(checkpointer=checkpointer or InMemorySaver())

    def _log(
        self,
        state: Mapping[str, Any],
        *,
        event_type: str,
        stage: str,
        payload: Mapping[str, Any] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        try:
            self.publisher.publish(
                ExecutionEvent.create(
                    session_id=str(state.get("session_id") or "unknown"),
                    request_id=state.get("request_id") or None,
                    event_type=event_type,
                    stage=stage,
                    payload=payload,
                    duration_ms=duration_ms,
                )
            )
        except Exception:
            # Observability must never change the planning outcome.
            return

    def _stage_node(
        self,
        stage: str,
        handler: Callable[[PlannerState], dict[str, Any]],
    ) -> Callable[[PlannerState], dict[str, Any]]:
        """Wrap a graph node with balanced enter/exit events and elapsed time."""

        @wraps(handler)
        def wrapped(state: PlannerState) -> dict[str, Any]:
            self._log(state, event_type=EventType.STAGE_ENTERED, stage=stage)
            started = perf_counter()
            try:
                update = handler(state)
            except Exception as error:
                self._log(
                    state,
                    event_type=EventType.STAGE_EXITED,
                    stage=stage,
                    payload={"status": "failed", "error_type": type(error).__name__},
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                raise
            self._log(
                state,
                event_type=EventType.STAGE_EXITED,
                stage=stage,
                payload={"status": "completed"},
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return update

        return wrapped

    def _analyze_request(self, state: PlannerState) -> dict[str, Any]:
        message = str(state.get("user_message") or "").strip()
        previous = dict(state.get("parsed_request") or {})
        current = self.now().astimezone(SEOUL)
        merged = dict(previous)
        analysis_source = "rules"
        analysis_reason = "명시된 장소·기관·시간·이동 상한을 규칙으로 추출했습니다."

        if self.analyzer is not None:
            try:
                raw_analysis = self.analyzer.analyze(
                    message,
                    previous=previous,
                    now=current,
                )
                merged.update(normalize_llm_fields(raw_analysis))
                analysis_source = "llm+rules"
                analysis_reason = str(raw_analysis.get("reason") or analysis_reason)
            except Exception:
                analysis_source = "rules_fallback"
                analysis_reason = "LLM 분석 실패 후 명시값 규칙으로 안전하게 분석했습니다."

        explicit = extract_explicit_fields(
            message,
            previous=previous,
            now=current,
        )
        merged.update(explicit)

        # The representative browser flow intentionally omits a departure time.
        # When all other visit constraints are explicit, "갈 곳 찾아줘" means a
        # current-departure search; keep the choice deterministic and observable.
        if (
            merged.get("departure_at") is None
            and merged.get("origin_query")
            and merged.get("institution_type")
            and merged.get("max_travel_seconds") is not None
        ):
            merged["departure_at"] = current.replace(microsecond=0)
            merged["departure_was_defaulted"] = True
            analysis_reason = (
                f"{analysis_reason} 출발 시각이 없어 현재 시각을 기본값으로 적용했습니다."
            )
        elif "departure_at" in explicit:
            merged["departure_was_defaulted"] = False

        previous_origin = previous.get("origin_query")
        next_origin = merged.get("origin_query")
        if next_origin and previous_origin and next_origin != previous_origin:
            for key in (
                "origin_longitude",
                "origin_latitude",
                "origin_name",
                "origin_address",
                "origin_place_id",
            ):
                merged.pop(key, None)

        next_basis = _candidate_basis(merged)
        keep_candidates = bool(state.get("candidates")) and next_basis == state.get(
            "candidate_basis"
        )
        update = {
            "parsed_request": merged,
            "analysis_source": analysis_source,
            "analysis_reason": analysis_reason,
            "plan": [],
            "missing_fields": [],
            "candidates": list(state.get("candidates") or []) if keep_candidates else [],
            "candidate_basis": next_basis if keep_candidates else "",
            "candidate_index": 0,
            "current_candidate": {},
            "current_detail": {},
            "current_route": {},
            "visited_institution_ids": [],
            "replan_count": 0,
            "needs_replan": False,
            "exclusions": [],
            "selected_candidate": {},
            "tool_cache": dict(state.get("tool_cache") or {}),
            "tool_calls": [],
            "clarification": "",
            "stop_reason": "",
            "final_answer": "",
            "error": "",
        }
        self._log(
            state,
            event_type=(
                EventType.LLM_DECISION
                if analysis_source.startswith("llm")
                else EventType.ANALYSIS_COMPLETED
            ),
            stage="analyze_request",
            payload={
                "decision_maker": "llm" if analysis_source.startswith("llm") else "rules",
                "source": analysis_source,
                "reason": analysis_reason,
                "extracted_fields": sorted(merged),
            },
        )
        return update

    def _build_plan(self, state: PlannerState) -> dict[str, Any]:
        request = state.get("parsed_request") or {}
        missing = _missing_fields(request)
        plan: list[str] = []
        if request.get("origin_longitude") is None and request.get("origin_query"):
            plan.append("search_place")
        if not missing or missing == ["origin"]:
            plan.extend(
                [
                    "search_nearby_institutions",
                    "get_institution_detail",
                    "get_driving_route",
                    "evaluate_visit",
                ]
            )
        elif request.get("origin_query"):
            # Resolve an explicitly supplied place before asking only for the
            # remaining conditions. This is also the required Tool-selection path.
            plan = list(dict.fromkeys(plan))
        self._log(
            state,
            event_type=EventType.PLAN_CREATED,
            stage="build_plan",
            payload={"steps": plan, "missing_fields": missing},
        )
        return {"plan": plan, "missing_fields": missing}

    def _invoke_tool(
        self,
        state: PlannerState,
        name: str,
        arguments: dict[str, Any],
        cache: dict[str, dict[str, Any]],
        calls: list[str],
    ) -> ToolResult:
        key = _cache_key(name, arguments)
        if key in cache:
            self._log(
                state,
                event_type=EventType.TOOL_CACHE_HIT,
                stage="execute_tools",
                payload={
                    "tool": name,
                    "arguments": arguments,
                    "ok": bool(cache[key].get("ok")),
                    "attempt": int(state.get("replan_count") or 0),
                },
            )
            calls.append(f"{name}:cache")
            return ToolResult.from_dict(cache[key])

        self._log(
            state,
            event_type=EventType.TOOL_REQUESTED,
            stage="execute_tools",
            payload={
                "tool": name,
                "arguments": arguments,
                "attempt": int(state.get("replan_count") or 0),
            },
        )
        started = perf_counter()
        result = self.registry.invoke(name, arguments)
        duration_ms = int((perf_counter() - started) * 1000)
        cache[key] = result.to_dict()
        calls.append(name)
        self._log(
            state,
            event_type=EventType.TOOL_RESPONDED,
            stage="execute_tools",
            payload={
                "tool": name,
                "ok": result.ok,
                "error_code": result.error.code if result.error else None,
                # Tool error messages are curated, upstream-free text.
                "error_message": result.error.message if result.error else None,
                "attempt": int(state.get("replan_count") or 0),
            },
            duration_ms=duration_ms,
        )
        return result

    def _execute_tools(self, state: PlannerState) -> dict[str, Any]:
        request = dict(state.get("parsed_request") or {})
        cache = dict(state.get("tool_cache") or {})
        calls = list(state.get("tool_calls") or [])
        update: dict[str, Any] = {
            "current_candidate": {},
            "current_detail": {},
            "current_route": {},
            "needs_replan": False,
        }

        if request.get("origin_longitude") is None or request.get("origin_latitude") is None:
            origin_query = str(request.get("origin_query") or "").strip()
            if not origin_query:
                update["clarification"] = "출발지를 알려 주세요. 예: ‘성남 판교역 신분당선’."
                return update
            place_result = self._invoke_tool(
                state,
                "search_place",
                {"query": origin_query, "region_hint": None},
                cache,
                calls,
            )
            update.update({"tool_cache": cache, "tool_calls": calls})
            if not place_result.ok:
                update["stop_reason"] = place_result.error.message if place_result.error else "장소 검색 실패"
                update["error"] = place_result.error.code if place_result.error else "PLACE_SEARCH_FAILED"
                return update
            place_data = place_result.data or {}
            places = list(place_data.get("candidates") or [])
            if place_data.get("ambiguous"):
                choices = ", ".join(
                    f"{item.get('name')} ({item.get('address')})" for item in places[:3]
                )
                update["clarification"] = (
                    "동명 장소가 있어 출발지를 확인해야 합니다. "
                    f"어느 곳인가요? {choices}"
                )
                return update
            selected_place = places[0]
            request.update(
                {
                    "origin_name": selected_place.get("name") or origin_query,
                    "origin_address": selected_place.get("address"),
                    "origin_place_id": selected_place.get("place_id"),
                    "origin_longitude": selected_place.get("longitude"),
                    "origin_latitude": selected_place.get("latitude"),
                }
            )
            update["parsed_request"] = request

        missing = _missing_fields(request)
        if missing:
            labels = ", ".join(MISSING_LABELS[field] for field in missing)
            update.update(
                {
                    "missing_fields": missing,
                    "clarification": f"계산하려면 {labels}을(를) 더 알려 주세요.",
                    "tool_cache": cache,
                    "tool_calls": calls,
                }
            )
            return update

        candidates = list(state.get("candidates") or [])
        basis = _candidate_basis(request)
        if not candidates or state.get("candidate_basis") != basis:
            nearby_result = self._invoke_tool(
                state,
                "search_nearby_institutions",
                {
                    "longitude": request["origin_longitude"],
                    "latitude": request["origin_latitude"],
                    "institution_type": request["institution_type"],
                    "page": 1,
                },
                cache,
                calls,
            )
            if not nearby_result.ok:
                update.update(
                    {
                        "stop_reason": nearby_result.error.message if nearby_result.error else "후보 조회 실패",
                        "error": nearby_result.error.code if nearby_result.error else "CANDIDATE_SEARCH_FAILED",
                        "tool_cache": cache,
                        "tool_calls": calls,
                    }
                )
                return update
            candidates = list((nearby_result.data or {}).get("candidates") or [])
            update.update({"candidates": candidates, "candidate_basis": basis})

        visited = set(state.get("visited_institution_ids") or [])
        candidate = next(
            (
                item
                for item in candidates
                if str(item.get("institution_id") or "") not in visited
            ),
            None,
        )
        if candidate is None:
            update.update(
                {
                    "stop_reason": "확인할 수 있는 새 후보가 남아 있지 않습니다.",
                    "tool_cache": cache,
                    "tool_calls": calls,
                }
            )
            return update

        departure = _datetime(request.get("departure_at"))
        detail_arguments: dict[str, Any] = {
            "institution_id": candidate["institution_id"],
            "institution_type": request["institution_type"],
            "visit_date": departure.date().isoformat() if departure else "",
        }
        if request.get("is_public_holiday") is not None:
            detail_arguments["is_public_holiday"] = request["is_public_holiday"]
        detail_result = self._invoke_tool(
            state,
            "get_institution_detail",
            detail_arguments,
            cache,
            calls,
        )
        update.update(
            {
                "current_candidate": candidate,
                "current_detail": detail_result.to_dict(),
                "tool_cache": cache,
                "tool_calls": calls,
            }
        )
        if not detail_result.ok:
            return update

        detail = detail_result.data or {}
        destination_longitude = detail.get("longitude") or candidate.get("longitude")
        destination_latitude = detail.get("latitude") or candidate.get("latitude")
        route_result = self._invoke_tool(
            state,
            "get_driving_route",
            {
                "origin": {
                    "longitude": request["origin_longitude"],
                    "latitude": request["origin_latitude"],
                },
                "destination": {
                    "longitude": destination_longitude,
                    "latitude": destination_latitude,
                },
                "departure_at": departure.isoformat() if departure else "",
            },
            cache,
            calls,
        )
        update.update(
            {
                "current_route": route_result.to_dict(),
                "tool_cache": cache,
                "tool_calls": calls,
            }
        )
        return update

    @staticmethod
    def _opening_intervals(detail: Mapping[str, Any]) -> list[OpeningInterval] | None:
        raw_intervals = detail.get("opening_intervals")
        if raw_intervals is None:
            return None
        intervals: list[OpeningInterval] = []
        for raw in raw_intervals:
            start = _datetime(raw.get("start"))
            end = _datetime(raw.get("end"))
            if start and end:
                intervals.append(OpeningInterval(start=start, end=end))
        return intervals

    @staticmethod
    def _remaining_until_close(
        departure: datetime,
        intervals: list[OpeningInterval] | None,
    ) -> int | None:
        if not intervals:
            return None
        active = next(
            (interval for interval in intervals if interval.start <= departure < interval.end),
            None,
        )
        return int((active.end - departure).total_seconds()) if active else None

    def _judge_constraints(self, state: PlannerState) -> dict[str, Any]:
        if state.get("clarification") or state.get("stop_reason"):
            return {"needs_replan": False}
        candidate = state.get("current_candidate") or {}
        if not candidate:
            return {
                "needs_replan": False,
                "stop_reason": "판단할 후보가 없습니다.",
            }
        request = state.get("parsed_request") or {}
        departure = _datetime(request.get("departure_at"))
        detail_result = ToolResult.from_dict(state.get("current_detail") or {"ok": False})
        route_result = ToolResult.from_dict(state.get("current_route") or {"ok": False})

        if not detail_result.ok:
            code = detail_result.error.code if detail_result.error else "DETAIL_UNAVAILABLE"
            reason = detail_result.error.message if detail_result.error else "기관 상세정보를 확인할 수 없습니다."
            decision = None
            detail: dict[str, Any] = {}
            route: dict[str, Any] = {}
        else:
            detail = detail_result.data or {}
            route = route_result.data or {} if route_result.ok else {}
            intervals = self._opening_intervals(detail)
            decision = evaluate_visit(
                departure_at=departure,
                travel_duration_seconds=route.get("duration_seconds") if route_result.ok else None,
                max_travel_seconds=int(request["max_travel_seconds"]),
                opening_intervals=intervals,
            )
            code = decision.code.value
            reason = decision.reason
            if not route_result.ok:
                remaining = self._remaining_until_close(departure, intervals)
                route_reason = route_result.error.message if route_result.error else reason
                if remaining is not None:
                    reason = (
                        f"출발 시각 기준 마감까지 {_format_seconds(remaining)} 남았지만 "
                        f"{route_reason}"
                    )
                else:
                    reason = route_reason

        institution_id = str(candidate.get("institution_id") or "")
        visited = list(state.get("visited_institution_ids") or [])
        if institution_id and institution_id not in visited:
            visited.append(institution_id)

        if decision is not None and decision.eligible:
            selected = {
                **candidate,
                **detail,
                **route,
                "expected_arrival_at": decision.expected_arrival_at.isoformat()
                if decision.expected_arrival_at
                else None,
                "seconds_until_close": decision.seconds_until_close,
                "decision_code": code,
                "selection_reason": reason,
            }
            self._log(
                state,
                event_type=EventType.CANDIDATE_SELECTED,
                stage="judge_constraints",
                payload={
                    "institution_id": institution_id,
                    "name": candidate.get("name"),
                    "code": code,
                    "reason": reason,
                    "attempt": int(state.get("replan_count") or 0),
                },
            )
            return {
                "visited_institution_ids": visited,
                "selected_candidate": selected,
                "needs_replan": False,
            }

        exclusion = {
            "institution_id": institution_id,
            "name": candidate.get("name"),
            "code": code,
            "reason": reason,
            "expected_arrival_at": (
                decision.expected_arrival_at.isoformat()
                if decision is not None and decision.expected_arrival_at
                else None
            ),
        }
        exclusions = [*(state.get("exclusions") or []), exclusion]
        remaining_candidates = any(
            str(item.get("institution_id") or "") not in set(visited)
            for item in (state.get("candidates") or [])
        )
        within_limit = int(state.get("replan_count") or 0) < self.settings.replan_limit
        needs_replan = remaining_candidates and within_limit
        stop_reason = ""
        if not needs_replan:
            if remaining_candidates and not within_limit:
                stop_reason = f"재계획 상한 {self.settings.replan_limit}회에 도달했습니다."
            else:
                stop_reason = "조회한 후보 중 조건을 충족하는 기관이 없습니다."
        self._log(
            state,
            event_type=EventType.CANDIDATE_EXCLUDED,
            stage="judge_constraints",
            payload={
                "institution_id": institution_id,
                "name": candidate.get("name"),
                "code": code,
                "reason": reason,
                "attempt": int(state.get("replan_count") or 0),
                "will_replan": needs_replan,
                "stop_reason": stop_reason or None,
            },
        )
        return {
            "visited_institution_ids": visited,
            "exclusions": exclusions,
            "needs_replan": needs_replan,
            "stop_reason": stop_reason,
        }

    @staticmethod
    def _after_judgment(state: PlannerState) -> str:
        return "replan" if state.get("needs_replan") else "respond"

    def _replan(self, state: PlannerState) -> dict[str, Any]:
        count = int(state.get("replan_count") or 0) + 1
        self._log(
            state,
            event_type=EventType.PLAN_REPLANNED,
            stage="replan",
            payload={
                "replan_count": count,
                "limit": self.settings.replan_limit,
                "reason": (state.get("exclusions") or [{}])[-1].get("reason"),
                "visited_institution_ids": state.get("visited_institution_ids") or [],
            },
        )
        return {
            "replan_count": count,
            "needs_replan": False,
            "current_candidate": {},
            "current_detail": {},
            "current_route": {},
        }

    def _generate_response(self, state: PlannerState) -> dict[str, Any]:
        if state.get("clarification"):
            answer = str(state["clarification"])
        elif state.get("selected_candidate"):
            selected = state["selected_candidate"]
            intervals = selected.get("opening_intervals") or []
            if intervals:
                hours = (
                    f"{_format_datetime(intervals[0].get('start'))} ~ "
                    f"{_format_datetime(intervals[0].get('end'))}"
                )
            else:
                hours = "확인 필요"
            lines = [
                f"{selected.get('name')}을(를) 방문 후보로 선택했습니다.",
                f"주소: {selected.get('address')}",
                f"예상 주행시간: {_format_seconds(selected.get('duration_seconds'))}",
                f"예상 도착: {_format_datetime(selected.get('expected_arrival_at'))}",
                f"적용 운영시간: {hours}",
                f"선택 근거: {selected.get('selection_reason')}",
            ]
            exclusions = state.get("exclusions") or []
            if exclusions:
                lines.append("제외 후보: " + "; ".join(
                    f"{item.get('name')} - {item.get('reason')}" for item in exclusions
                ))
            lines.append(MEDICAL_NOTICE)
            answer = "\n".join(lines)
        else:
            lines = [
                "조건을 충족하는 방문 후보를 확정하지 못했습니다.",
                f"종료 사유: {state.get('stop_reason') or '확인 가능한 결과가 없습니다.'}",
            ]
            exclusions = state.get("exclusions") or []
            if exclusions:
                lines.append("확인한 후보: " + "; ".join(
                    f"{item.get('name')} - {item.get('reason')}" for item in exclusions
                ))
            lines.append(MEDICAL_NOTICE)
            answer = "\n".join(lines)
        self._log(
            state,
            event_type=EventType.RESPONSE_GENERATED,
            stage="generate_response",
            payload={
                "selected": bool(state.get("selected_candidate")),
                "needs_input": bool(state.get("clarification")),
                "replan_count": state.get("replan_count") or 0,
                "stop_reason": state.get("stop_reason") or None,
            },
        )
        return {"final_answer": answer}

    def run(
        self,
        *,
        session_id: str,
        message: str,
        request_id: str | None = None,
    ) -> PlannerState:
        return self.graph.invoke(
            {
                "session_id": session_id,
                "request_id": request_id or uuid4().hex,
                "user_message": message,
            },
            config={
                "configurable": {"thread_id": session_id},
                "recursion_limit": max(30, self.settings.replan_limit * 5 + 15),
            },
        )

    def graph_mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()
