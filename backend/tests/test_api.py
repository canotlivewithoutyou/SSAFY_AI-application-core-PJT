from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, Coroutine

from fastapi import HTTPException

from backend.app.api import chat as chat_api
from backend.app.api import health as health_api
from backend.app.api import logs as logs_api
from backend.app.api import plans as plans_api
from backend.app.config import get_settings
from backend.app.database import initialize_database
from backend.app.main import app
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.plan import PlanCreate, PlanUpdate


def complete_without_await(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Complete an async route that intentionally contains no await points.

    The Codex Windows sandbox blocks the local socket pair used to create an
    asyncio event loop. These API routes perform short synchronous SQLite work,
    so their contract can still be exercised directly and deterministically.
    """

    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    finally:
        coroutine.close()
    raise AssertionError("Route unexpectedly reached an await point")


class APIContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "api-test.db"
        initialize_database(self.database_path)
        self.settings = replace(get_settings(), database_path=self.database_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_routes_chat_logging_and_plan_crud(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn(
            "/app",
            {route.path for route in app.routes if hasattr(route, "path")},
        )
        self.assertTrue(
            {
                "/api/v1/health",
                "/api/v1/meta/tools",
                "/api/v1/meta/graph",
                "/api/v1/chat",
                "/api/v1/plans",
                "/api/v1/plans/{plan_id}",
                "/api/v1/logs",
                "/api/v1/logs/{event_id}",
            }.issubset(paths)
        )

        health = complete_without_await(health_api.health(self.settings))
        self.assertEqual(health["database"], "ready")

        tools = complete_without_await(health_api.tool_catalog(self.settings))
        self.assertEqual(len(tools["tools"]), 4)
        self.assertTrue(all(tool["implemented"] for tool in tools["tools"]))

        graph = complete_without_await(health_api.graph_structure(self.settings))
        self.assertIn("analyze_request", graph["graph"])

        chat = complete_without_await(
            chat_api.chat(
                ChatRequest(session_id="api-test", message="이 서비스는 어떻게 써?"),
                self.settings,
            )
        )
        self.assertEqual(chat.status, "completed")
        self.assertEqual(chat.tool_calls, [])

        payload = PlanCreate.model_validate(
            {
                "institution_type": "pharmacy",
                "institution_id": "SMOKE-PHARMACY",
                "institution_name": "통합검증약국",
                "institution_address": "경기 성남시 테스트로 1",
                "visit_date": "2026-11-19",
                "origin_name": "성남 판교역 신분당선",
                "origin_longitude": 127.11119782955879,
                "origin_latitude": 37.39477752734142,
                "destination_longitude": 127.115,
                "destination_latitude": 37.397,
                "departure_at": "2026-11-19T20:56:00+09:00",
                "expected_arrival_at": "2026-11-19T20:59:05+09:00",
                "travel_duration_seconds": 185,
                "operation_start": "2026-11-19T09:00:00+09:00",
                "operation_end": "2026-11-19T21:00:00+09:00",
                "selection_reason": "마감 55초 전 도착 예상",
            }
        )
        created = complete_without_await(plans_api.create_plan(payload, self.settings))
        plan_id = created.plan.id

        listed = complete_without_await(plans_api.list_plans(None, 100, self.settings))
        self.assertEqual([item.id for item in listed], [plan_id])

        response = complete_without_await(plans_api.delete_plan(plan_id, self.settings))
        self.assertEqual(response.status_code, 204)

        logs = complete_without_await(logs_api.list_logs(None, 100, self.settings))
        self.assertEqual(len(logs), 2)

    def test_invalid_plan_update_returns_422_and_keeps_plan(self) -> None:
        payload = PlanCreate.model_validate(
            {
                "institution_type": "pharmacy",
                "institution_name": "검증약국",
                "institution_address": "경기 성남시 테스트로 1",
                "visit_date": "2026-11-20",
                "origin_name": "판교역",
                "origin_longitude": 127.111,
                "origin_latitude": 37.394,
                "destination_longitude": 127.112,
                "destination_latitude": 37.396,
                "departure_at": "2026-11-20T21:00:00+09:00",
                "expected_arrival_at": "2026-11-20T21:03:34+09:00",
                "travel_duration_seconds": 214,
                "operation_start": "2026-11-20T09:00:00+09:00",
                "operation_end": "2026-11-20T22:00:00+09:00",
                "selection_reason": "원래 근거",
            }
        )
        plan_id = complete_without_await(plans_api.create_plan(payload, self.settings)).plan.id

        # Departure 21:58 + 214s arrives 22:01:34, after closing at 22:00.
        change = PlanUpdate.model_validate(
            {
                "departure_at": "2026-11-20T21:58:00+09:00",
                "expected_arrival_at": "2026-11-20T22:01:34+09:00",
            }
        )
        with self.assertRaises(HTTPException) as raised:
            complete_without_await(plans_api.update_plan(plan_id, change, self.settings))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("운영 구간", raised.exception.detail)
        self.assertNotIn("Value error", raised.exception.detail)

        unchanged = complete_without_await(plans_api.get_plan(plan_id, self.settings))
        self.assertEqual(unchanged.departure_at.hour, 21)
        self.assertEqual(unchanged.departure_at.minute, 0)


if __name__ == "__main__":
    unittest.main()

