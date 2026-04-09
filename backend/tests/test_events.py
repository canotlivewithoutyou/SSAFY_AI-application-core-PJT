"""F3012~F3013: event publishing is decoupled from the Logging Agent."""

from __future__ import annotations

import ast
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from backend.app.agents.logging_agent import LoggingAgent, subscribe_logging_agent
from backend.app.agents.planner import PlannerAgent
from backend.app.config import get_settings
from backend.app.database import initialize_database
from backend.app.events import EventBus, EventType, ExecutionEvent, sanitize_payload
from backend.app.repositories.logs import list_events, record_event
from backend.app.services.trace import summarize_request_events
from backend.tests.test_planner import SEOUL, FakeRegistry, RuleAnalyzer


PLANNER_SOURCE = Path(__file__).resolve().parents[1] / "app" / "agents" / "planner.py"
MESSAGE = "성남 판교역에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘"


class ExplodingSubscriber:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, event: ExecutionEvent) -> None:
        self.calls += 1
        raise RuntimeError("subscriber storage is down")


class EventPublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "events.db"
        initialize_database(self.database_path)
        self.settings = replace(
            get_settings(),
            database_path=self.database_path,
            openai_api_key="",
            openai_model="",
            replan_limit=5,
        )
        self.now = datetime(2026, 11, 19, 20, 0, tzinfo=SEOUL)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def agent(self, publisher=None, registry=None, settings=None) -> PlannerAgent:
        return PlannerAgent(
            settings or self.settings,
            registry=registry or FakeRegistry(),
            analyzer=RuleAnalyzer(),
            now=lambda: self.now,
            publisher=publisher,
        )

    def logged_agent(self, **kwargs) -> PlannerAgent:
        bus = EventBus()
        subscribe_logging_agent(bus, self.database_path)
        return self.agent(publisher=bus, **kwargs)

    def test_planner_does_not_import_logging_or_storage(self) -> None:
        tree = ast.parse(PLANNER_SOURCE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for forbidden in ("logging_agent", "repositories", "database", "sqlite3"):
            self.assertFalse(
                any(forbidden in module for module in imported),
                f"planner.py imports {forbidden}",
            )

    def test_planner_responds_without_any_subscriber(self) -> None:
        bus = EventBus()
        self.assertEqual(bus.subscriber_count, 0)
        result = self.agent(publisher=bus).run(session_id="no-subscriber", message=MESSAGE)
        self.assertEqual(result["selected_candidate"]["institution_id"], "C2")
        self.assertEqual(list_events(self.database_path), [])

        default_result = self.agent().run(session_id="default-publisher", message=MESSAGE)
        self.assertEqual(default_result["selected_candidate"]["institution_id"], "C2")

    def test_failing_subscriber_does_not_break_planner(self) -> None:
        bus = EventBus()
        exploding = ExplodingSubscriber()
        bus.subscribe(exploding)
        subscribe_logging_agent(bus, self.database_path)
        result = self.agent(publisher=bus).run(session_id="failing-subscriber", message=MESSAGE)

        self.assertEqual(result["selected_candidate"]["institution_id"], "C2")
        self.assertIn("의료 상담을 대신하지 않습니다", result["final_answer"])
        self.assertGreater(exploding.calls, 0)
        self.assertEqual(bus.failed_deliveries, exploding.calls)
        # The healthy Logging Agent still receives every event.
        self.assertEqual(
            len(list_events(self.database_path, session_id="failing-subscriber", limit=500)),
            exploding.calls,
        )

    def test_logging_agent_storage_failure_does_not_break_planner(self) -> None:
        bus = EventBus()
        subscribe_logging_agent(bus, Path(self.temp.name) / "missing-dir" / "x.db")
        result = self.agent(publisher=bus).run(session_id="broken-db", message=MESSAGE)
        self.assertEqual(result["selected_candidate"]["institution_id"], "C2")
        self.assertGreater(bus.failed_deliveries, 0)

    def test_unsubscribed_logging_agent_stops_storing(self) -> None:
        bus = EventBus()
        unsubscribe = subscribe_logging_agent(bus, self.database_path)
        unsubscribe()
        self.agent(publisher=bus).run(session_id="unsubscribed", message=MESSAGE)
        self.assertEqual(list_events(self.database_path), [])

    def test_logging_agent_stores_session_and_request_fields(self) -> None:
        agent = self.logged_agent()
        agent.run(session_id="stored-session", message=MESSAGE, request_id="req-1")
        events = list_events(
            self.database_path, session_id="stored-session", limit=500, order="asc"
        )
        self.assertTrue(events)
        for event in events:
            self.assertEqual(event["session_id"], "stored-session")
            self.assertEqual(event["request_id"], "req-1")
            for field in ("event_type", "stage", "payload", "duration_ms", "created_at"):
                self.assertIn(field, event)
        self.assertEqual(events[0]["event_type"], EventType.STAGE_ENTERED)
        self.assertEqual(events[-1]["event_type"], EventType.STAGE_EXITED)
        self.assertIn(EventType.RESPONSE_GENERATED, {event["event_type"] for event in events})

    def test_logging_agent_is_plain_storage_without_llm(self) -> None:
        tree = ast.parse((PLANNER_SOURCE.parent / "logging_agent.py").read_text(encoding="utf-8"))
        modules = {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        for forbidden in ("llm", "openai", "langchain", "planner"):
            self.assertFalse(any(forbidden in module for module in modules), forbidden)
        LoggingAgent(self.database_path)(
            ExecutionEvent.create(
                session_id="direct", request_id="r", event_type="x", stage="s", payload={"a": 1}
            )
        )
        self.assertEqual(list_events(self.database_path)[0]["payload"], {"a": 1})

    def test_stage_enter_and_exit_events_are_paired(self) -> None:
        self.logged_agent().run(session_id="stages", message=MESSAGE, request_id="r1")
        events = list_events(self.database_path, session_id="stages", limit=500, order="asc")
        depth: dict[str, int] = {}
        for event in events:
            if event["event_type"] == EventType.STAGE_ENTERED:
                depth[event["stage"]] = depth.get(event["stage"], 0) + 1
            elif event["event_type"] == EventType.STAGE_EXITED:
                self.assertGreater(depth.get(event["stage"], 0), 0, "exit before enter")
                depth[event["stage"]] -= 1
                self.assertIsNotNone(event["duration_ms"])
                self.assertEqual(event["payload"]["status"], "completed")
        self.assertTrue(depth)
        self.assertTrue(all(value == 0 for value in depth.values()))
        exited = [e["stage"] for e in events if e["event_type"] == EventType.STAGE_EXITED]
        self.assertEqual(
            exited,
            [
                "analyze_request",
                "build_plan",
                "execute_tools",
                "judge_constraints",
                "replan",
                "execute_tools",
                "judge_constraints",
                "generate_response",
            ],
        )

    def test_tool_request_and_response_with_duration(self) -> None:
        self.logged_agent().run(session_id="tools", message=MESSAGE, request_id="r1")
        events = list_events(self.database_path, session_id="tools", limit=500, order="asc")
        requested = [e for e in events if e["event_type"] == EventType.TOOL_REQUESTED]
        responded = [e for e in events if e["event_type"] == EventType.TOOL_RESPONDED]
        self.assertEqual(
            [e["payload"]["tool"] for e in requested],
            [e["payload"]["tool"] for e in responded],
        )
        self.assertEqual(
            [e["payload"]["tool"] for e in responded],
            [
                "search_place",
                "search_nearby_institutions",
                "get_institution_detail",
                "get_driving_route",
                "get_institution_detail",
                "get_driving_route",
            ],
        )
        for event in responded:
            self.assertIsInstance(event["duration_ms"], int)
            self.assertGreaterEqual(event["duration_ms"], 0)
            self.assertIn("ok", event["payload"])
        failed = [e for e in responded if not e["payload"]["ok"]]
        self.assertEqual(failed[0]["payload"]["error_code"], "ROUTE_UNAVAILABLE")
        self.assertIn("경로 코드 104", failed[0]["payload"]["error_message"])

    def test_decision_reason_is_recorded(self) -> None:
        self.logged_agent().run(session_id="decision", message=MESSAGE, request_id="r1")
        events = list_events(self.database_path, session_id="decision", limit=500, order="asc")
        decisions = [
            e
            for e in events
            if e["event_type"] in (EventType.ANALYSIS_COMPLETED, EventType.LLM_DECISION)
        ]
        self.assertEqual(len(decisions), 1)
        self.assertTrue(decisions[0]["payload"]["reason"])
        self.assertIn(decisions[0]["payload"]["decision_maker"], ("rules", "llm"))
        excluded = [e for e in events if e["event_type"] == EventType.CANDIDATE_EXCLUDED]
        selected = [e for e in events if e["event_type"] == EventType.CANDIDATE_SELECTED]
        self.assertTrue(excluded[0]["payload"]["reason"])
        self.assertTrue(selected[0]["payload"]["reason"])

    def test_tool_failure_then_replan_trace(self) -> None:
        self.logged_agent().run(session_id="replan-trace", message=MESSAGE, request_id="r1")
        summary = summarize_request_events(
            list_events(self.database_path, session_id="replan-trace", limit=500, order="asc")
        )
        kinds = [item["kind"] for item in summary["timeline"]]
        failed_index = next(
            i for i, item in enumerate(summary["timeline"])
            if item["kind"] == "tool" and not item["ok"]
        )
        self.assertEqual(summary["timeline"][failed_index]["tool"], "get_driving_route")
        self.assertEqual(kinds[failed_index + 1], "candidate_excluded")
        self.assertTrue(summary["timeline"][failed_index + 1]["will_replan"])
        self.assertEqual(kinds[failed_index + 2], "replan")
        self.assertEqual(summary["timeline"][failed_index + 2]["replan_count"], 1)
        self.assertIn("경로 코드 104", summary["timeline"][failed_index + 2]["reason"])
        self.assertEqual(kinds[-1], "candidate_selected")
        self.assertEqual(summary["replan_count"], 1)
        self.assertEqual(summary["failed_tool_count"], 1)
        self.assertEqual(summary["excluded_count"], 1)
        self.assertEqual(summary["selected"]["institution_id"], "C2")
        self.assertEqual([tool["order"] for tool in summary["tools"]], [1, 2, 3, 4, 5, 6])

    def test_replan_limit_trace(self) -> None:
        settings = replace(self.settings, replan_limit=1)
        self.logged_agent(
            registry=FakeRegistry(candidate_count=3, all_routes_fail=True), settings=settings
        ).run(session_id="limit-trace", message=MESSAGE, request_id="r1")
        summary = summarize_request_events(
            list_events(self.database_path, session_id="limit-trace", limit=500, order="asc")
        )
        replans = [item for item in summary["timeline"] if item["kind"] == "replan"]
        excluded = [item for item in summary["timeline"] if item["kind"] == "candidate_excluded"]
        self.assertEqual(len(replans), 1)
        self.assertEqual(replans[0]["limit"], 1)
        self.assertEqual(len(excluded), 2)
        self.assertTrue(excluded[0]["will_replan"])
        self.assertFalse(excluded[1]["will_replan"])
        self.assertIn("재계획 상한 1회", excluded[1]["stop_reason"])
        self.assertIn("재계획 상한 1회", summary["stop_reason"])
        self.assertIsNone(summary["selected"])
        self.assertEqual(summary["timeline"][-1]["kind"], "candidate_excluded")

    def test_cache_hits_are_marked_in_trace(self) -> None:
        agent = self.logged_agent()
        agent.run(session_id="cache", message=MESSAGE, request_id="first")
        agent.run(session_id="cache", message="30분 뒤에 출발하면?", request_id="second")
        second = summarize_request_events(
            list_events(self.database_path, request_id="second", limit=500, order="asc")
        )
        self.assertGreater(second["cache_hit_count"], 0)
        self.assertTrue(any(tool["cached"] for tool in second["tools"]))
        self.assertTrue(all(tool["duration_ms"] is None for tool in second["tools"] if tool["cached"]))


class SecretMaskingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "mask.db"
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_key_like_values_are_masked(self) -> None:
        payload = {
            "query": "판교역",
            "note": "Authorization: KakaoAK abcdef1234567890",
            "llm": "sk-proj-AbCdEf0123456789xyz",
            "url": "https://apis.example/getList?serviceKey=Zx9%2Bqq77&pageNo=1",
            "opaque": "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
            "nested": [{"Authorization": "Bearer abc.def.ghi"}],
            "missing_settings": ["OPENAI_API_KEY", "KAKAO_REST_API_KEY"],
            "departure_at": "2026-11-19T21:00:00+09:00",
        }
        stored = record_event(
            self.database_path,
            session_id="mask",
            event_type=EventType.TOOL_REQUESTED,
            stage="execute_tools",
            payload=payload,
        )["payload"]
        text = repr(stored)
        for secret in ("abcdef1234567890", "sk-proj", "Zx9%2Bqq77", "a1B2c3D4e5F6", "abc.def.ghi"):
            self.assertNotIn(secret, text)
        self.assertEqual(stored["query"], "판교역")
        self.assertEqual(stored["nested"][0]["Authorization"], "[REDACTED]")
        self.assertEqual(stored["missing_settings"], ["OPENAI_API_KEY", "KAKAO_REST_API_KEY"])
        self.assertEqual(stored["departure_at"], "2026-11-19T21:00:00+09:00")
        self.assertIn("pageNo=1", stored["url"])

    def test_event_payload_is_sanitized_before_any_subscriber(self) -> None:
        received: list[ExecutionEvent] = []
        bus = EventBus()
        bus.subscribe(received.append)
        bus.publish(
            ExecutionEvent.create(
                session_id="s",
                event_type="x",
                stage="y",
                payload={"service_key": "plain-value", "headers": {"authorization": "x"}},
            )
        )
        self.assertEqual(received[0].payload["service_key"], "[REDACTED]")
        self.assertEqual(received[0].payload["headers"]["authorization"], "[REDACTED]")
        self.assertEqual(sanitize_payload({"query": "약국"}), {"query": "약국"})


if __name__ == "__main__":
    unittest.main()
