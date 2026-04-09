"""F3014 and F3019: session trace API, request isolation and chat trace contract."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from backend.app.agents.logging_agent import subscribe_logging_agent
from backend.app.agents.planner import PlannerAgent
from backend.app.api import chat as chat_api
from backend.app.api import logs as logs_api
from backend.app.config import get_settings
from backend.app.database import initialize_database
from backend.app.events import EventBus, EventType
from backend.app.main import app
from backend.app.repositories import logs as repository
from backend.app.schemas.chat import ChatRequest
from backend.app.services.chat import handle_chat
from backend.tests.test_api import complete_without_await
from backend.tests.test_planner import SEOUL, FakeRegistry, RuleAnalyzer


MESSAGE = "성남 판교역에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘"


class SessionTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "logs-api.db"
        initialize_database(self.database_path)
        # Fake, non-secret values so the planner path runs; no external call is made.
        self.settings = replace(
            get_settings(),
            database_path=self.database_path,
            openai_api_key="test-openai",
            openai_model="test-model",
            kakao_rest_api_key="test-kakao",
            nmc_service_key="test-nmc",
            replan_limit=5,
        )
        self.bus = EventBus()
        subscribe_logging_agent(self.bus, self.database_path)
        self.registry = FakeRegistry()
        self.agent = PlannerAgent(
            self.settings,
            registry=self.registry,
            analyzer=RuleAnalyzer(),
            now=lambda: datetime(2026, 11, 19, 20, 0, tzinfo=SEOUL),
            publisher=self.bus,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def chat(self, session_id: str, message: str, settings=None):
        return handle_chat(
            ChatRequest(session_id=session_id, message=message),
            settings or self.settings,
            publisher=self.bus,
            planner_factory=lambda _: self.agent,
        )

    def session_trace(self, session_id: str, request_id=None, latest=False):
        return complete_without_await(
            logs_api.get_session_logs(session_id, self.settings, request_id, latest)
        )

    def test_session_logs_are_returned_in_execution_order(self) -> None:
        response = self.chat("ordered", MESSAGE)
        trace = self.session_trace("ordered")
        ids = [event.id for event in trace.events]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(trace.events[0].event_type, EventType.REQUEST_RECEIVED)
        self.assertEqual(trace.events[-1].event_type, EventType.REQUEST_COMPLETED)
        self.assertEqual(trace.latest_request_id, response.request_id)
        self.assertIsNone(trace.summary)

        newest_first = complete_without_await(
            logs_api.list_logs("ordered", 500, self.settings, None, "desc")
        )
        oldest_first = complete_without_await(
            logs_api.list_logs("ordered", 500, self.settings, None, "asc")
        )
        self.assertEqual([e.id for e in newest_first], list(reversed(ids)))
        self.assertEqual([e.id for e in oldest_first], ids)

    def test_sessions_do_not_mix(self) -> None:
        self.chat("session-a", MESSAGE)
        self.chat("session-b", "이 서비스는 어떻게 써?")
        trace_a = self.session_trace("session-a")
        trace_b = self.session_trace("session-b")
        self.assertTrue(all(event.session_id == "session-a" for event in trace_a.events))
        self.assertTrue(all(event.session_id == "session-b" for event in trace_b.events))
        self.assertFalse({e.id for e in trace_a.events} & {e.id for e in trace_b.events})
        with self.assertRaises(HTTPException) as missing:
            self.session_trace("session-unknown")
        self.assertEqual(missing.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            self.session_trace("session-a", request_id=trace_b.latest_request_id)

    def test_requests_in_same_session_are_separated(self) -> None:
        first = self.chat("multi", MESSAGE)
        second = self.chat("multi", "30분 뒤에 출발하면?")
        self.assertNotEqual(first.request_id, second.request_id)

        whole = self.session_trace("multi")
        self.assertEqual(
            [run.request_id for run in whole.requests], [first.request_id, second.request_id]
        )
        self.assertEqual(whole.latest_request_id, second.request_id)
        self.assertEqual(sum(run.event_count for run in whole.requests), len(whole.events))

        latest = self.session_trace("multi", latest=True)
        self.assertEqual(latest.request_id, second.request_id)
        self.assertTrue(all(e.request_id == second.request_id for e in latest.events))
        self.assertEqual(latest.summary["status"], second.status)

        earlier = self.session_trace("multi", request_id=first.request_id)
        self.assertTrue(all(e.request_id == first.request_id for e in earlier.events))
        self.assertEqual(earlier.summary["replan_count"], 1)
        self.assertEqual(latest.summary["replan_count"], second.replan_count)
        self.assertGreater(latest.summary["cache_hit_count"], 0)

    def test_chat_response_trace_matches_recorded_tools(self) -> None:
        response = self.chat("contract", MESSAGE)
        self.assertEqual(response.status, "completed")
        self.assertTrue(response.request_id)
        summary = self.session_trace("contract", request_id=response.request_id).summary
        self.assertEqual([tool["tool"] for tool in summary["tools"]], response.tool_calls)
        self.assertEqual(summary["replan_count"], response.replan_count)
        self.assertEqual(summary["status"], "completed")
        self.assertTrue(summary["completed"])
        failed = [tool for tool in summary["tools"] if not tool["ok"]]
        self.assertEqual(failed[0]["tool"], "get_driving_route")
        self.assertEqual(failed[0]["order"], 4)
        self.assertIn("경로 코드 104", failed[0]["error_message"])
        self.assertEqual(
            [stage["stage"] for stage in summary["stages"]][:3],
            ["analyze_request", "build_plan", "execute_tools"],
        )

    def test_tool_free_request_has_zero_tool_calls(self) -> None:
        response = self.chat("help", "이 서비스는 어떻게 써?")
        self.assertEqual(response.tool_calls, [])
        summary = self.session_trace("help", request_id=response.request_id).summary
        self.assertEqual(summary["tool_call_count"], 0)
        self.assertEqual(summary["tools"], [])
        self.assertEqual(summary["stages"], [])
        self.assertEqual(sum(self.registry.calls.values()), 0)
        self.assertEqual(summary["status"], "completed")

    def test_setup_required_lists_names_without_values(self) -> None:
        settings = replace(self.settings, kakao_rest_api_key="", nmc_service_key="")
        response = self.chat("setup", MESSAGE, settings=settings)
        self.assertEqual(response.status, "setup_required")
        summary = self.session_trace("setup", request_id=response.request_id).summary
        self.assertEqual(summary["missing_settings"], ["KAKAO_REST_API_KEY", "NMC_SERVICE_KEY"])
        self.assertEqual(summary["tool_call_count"], 0)
        stored = repr([e.payload for e in self.session_trace("setup").events])
        self.assertNotIn("test-openai", stored)

    def test_list_detail_delete_and_no_update_api(self) -> None:
        self.chat("crud", "이 서비스는 어떻게 써?")
        listed = complete_without_await(logs_api.list_logs("crud", 100, self.settings, None, "desc"))
        self.assertEqual(len(listed), 2)
        detail = complete_without_await(logs_api.get_log(listed[0].id, self.settings))
        self.assertEqual(detail.id, listed[0].id)
        self.assertEqual(detail.request_id, listed[0].request_id)
        deleted = complete_without_await(logs_api.delete_log(listed[0].id, self.settings))
        self.assertEqual(deleted.status_code, 204)
        with self.assertRaises(HTTPException) as missing:
            complete_without_await(logs_api.get_log(listed[0].id, self.settings))
        self.assertEqual(missing.exception.status_code, 404)

        paths = app.openapi()["paths"]
        log_paths = {path: item for path, item in paths.items() if path.startswith("/api/v1/logs")}
        self.assertEqual(
            set(log_paths),
            {"/api/v1/logs", "/api/v1/logs/sessions/{session_id}", "/api/v1/logs/{event_id}"},
        )
        for item in log_paths.values():
            self.assertFalse({"put", "patch", "post"} & set(item))

    def test_api_route_uses_composition_bus(self) -> None:
        # The public route wires the Logging Agent through the composition root.
        help_response = complete_without_await(
            chat_api.chat(ChatRequest(session_id="route", message="사용법 알려줘"), self.settings)
        )
        self.assertTrue(help_response.request_id)
        trace = self.session_trace("route", request_id=help_response.request_id)
        self.assertEqual(
            [event.event_type for event in trace.events],
            [EventType.REQUEST_RECEIVED, EventType.REQUEST_COMPLETED],
        )


class LegacyDatabaseMigrationTests(unittest.TestCase):
    def test_existing_database_gains_request_id_and_keeps_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    duration_ms INTEGER,
                    created_at TEXT NOT NULL
                );
                INSERT INTO execution_logs (session_id, event_type, stage, payload_json, created_at)
                VALUES ('old', 'request.received', 'chat', '{}', '2026-11-19T11:00:00.000+00:00');
                """
            )
            connection.commit()
            connection.close()

            initialize_database(database_path)
            initialize_database(database_path)  # idempotent

            old = repository.list_events(database_path, session_id="old")
            self.assertEqual(len(old), 1)
            self.assertIsNone(old[0]["request_id"])
            repository.record_event(
                database_path,
                session_id="old",
                request_id="new-run",
                event_type="request.received",
                stage="chat",
            )
            trace = repository.get_session_trace(database_path, "old")
            self.assertEqual([run["request_id"] for run in trace["requests"]], [None, "new-run"])
            self.assertEqual(trace["latest_request_id"], "new-run")


if __name__ == "__main__":
    unittest.main()
