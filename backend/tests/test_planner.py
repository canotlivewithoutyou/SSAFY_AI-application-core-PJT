from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.agents.planner import PlannerAgent
from backend.app.config import get_settings
from backend.app.database import initialize_database
from backend.app.tools.contracts import failure, success


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


class RuleAnalyzer:
    def analyze(self, message, *, previous, now):
        return {"reason": "테스트 분석", "intent": "visit_plan"}


class FakeRegistry:
    def __init__(self, *, ambiguous=False, candidate_count=2, all_routes_fail=False):
        self.ambiguous = ambiguous
        self.candidate_count = candidate_count
        self.all_routes_fail = all_routes_fail
        self.calls = Counter()

    def invoke(self, name, arguments):
        self.calls[name] += 1
        if name == "search_place":
            places = [
                {
                    "place_id": "P1",
                    "name": "판교역 신분당선",
                    "address": "경기 성남시 분당구 판교역로 160",
                    "longitude": 127.1111,
                    "latitude": 37.3947,
                }
            ]
            if self.ambiguous:
                places.append(
                    {
                        "place_id": "P2",
                        "name": "판교역",
                        "address": "충남 서천군 판교면",
                        "longitude": 126.68,
                        "latitude": 36.15,
                    }
                )
            return success({"ambiguous": self.ambiguous, "candidates": places})
        if name == "search_nearby_institutions":
            candidates = [
                {
                    "institution_id": f"C{i}",
                    "institution_type": "pharmacy",
                    "name": f"후보{i}약국",
                    "address": f"경기 성남시 테스트로 {i}",
                    "longitude": 127.12 + i / 1000,
                    "latitude": 37.40 + i / 1000,
                }
                for i in range(1, self.candidate_count + 1)
            ]
            return success({"candidates": candidates})
        if name == "get_institution_detail":
            sequence = int(arguments["institution_id"][1:])
            close_at = (
                "2026-11-19T21:04:00+09:00"
                if sequence == 1
                else "2026-11-19T22:30:00+09:00"
            )
            return success(
                {
                    "institution_id": arguments["institution_id"],
                    "name": f"{arguments['institution_id']}약국",
                    "address": "경기 성남시 테스트로",
                    "longitude": 127.12 + sequence / 1000,
                    "latitude": 37.40 + sequence / 1000,
                    "hours_status": "confirmed",
                    "opening_intervals": [
                        {
                            "start": "2026-11-19T09:00:00+09:00",
                            "end": close_at,
                        }
                    ],
                }
            )
        if name == "get_driving_route":
            if self.all_routes_fail or arguments["destination"]["longitude"] < 127.122:
                return failure("ROUTE_UNAVAILABLE", "차량 경로 코드 104로 이동시간을 확인할 수 없습니다.")
            return success(
                {
                    "mode": "future",
                    "duration_seconds": 185,
                    "distance_meters": 523,
                    "departure_at": arguments["departure_at"],
                }
            )
        raise AssertionError(name)


class PlannerGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database_path = Path(self.temp.name) / "planner-agent.db"
        initialize_database(database_path)
        self.settings = replace(
            get_settings(),
            database_path=database_path,
            openai_api_key="",
            openai_model="",
            replan_limit=5,
        )
        self.now = datetime(2026, 11, 19, 20, 0, tzinfo=SEOUL)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_route_failure_replans_and_selects_next_candidate(self) -> None:
        registry = FakeRegistry()
        agent = PlannerAgent(
            self.settings,
            registry=registry,
            analyzer=RuleAnalyzer(),
            now=lambda: self.now,
        )
        result = agent.run(
            session_id="replan-session",
            message="성남 판교역에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘",
        )

        self.assertEqual(result["selected_candidate"]["institution_id"], "C2")
        self.assertEqual(result["replan_count"], 1)
        self.assertEqual(result["exclusions"][0]["code"], "route_unavailable")
        self.assertIn("마감까지 4분", result["exclusions"][0]["reason"])
        self.assertIn("경로 코드 104", result["exclusions"][0]["reason"])
        self.assertIn("제외 후보", result["final_answer"])
        self.assertIn("의료 상담을 대신하지 않습니다", result["final_answer"])

    def test_follow_up_keeps_origin_and_reuses_non_route_results(self) -> None:
        registry = FakeRegistry()
        agent = PlannerAgent(
            self.settings,
            registry=registry,
            analyzer=RuleAnalyzer(),
            now=lambda: self.now,
        )
        first = agent.run(
            session_id="memory-session",
            message="성남 판교역에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘",
        )
        counts_after_first = registry.calls.copy()
        second = agent.run(
            session_id="memory-session",
            message="30분 뒤에 출발하면?",
        )

        self.assertEqual(
            second["parsed_request"]["origin_longitude"],
            first["parsed_request"]["origin_longitude"],
        )
        self.assertEqual(second["parsed_request"]["departure_at"].hour, 21)
        self.assertEqual(second["parsed_request"]["departure_at"].minute, 30)
        self.assertEqual(registry.calls["search_place"], counts_after_first["search_place"])
        self.assertEqual(
            registry.calls["search_nearby_institutions"],
            counts_after_first["search_nearby_institutions"],
        )
        self.assertEqual(
            registry.calls["get_institution_detail"],
            counts_after_first["get_institution_detail"],
        )
        self.assertGreater(
            registry.calls["get_driving_route"],
            counts_after_first["get_driving_route"],
        )

    def test_replan_limit_stops_with_reason(self) -> None:
        registry = FakeRegistry(candidate_count=3, all_routes_fail=True)
        settings = replace(self.settings, replan_limit=1)
        agent = PlannerAgent(
            settings,
            registry=registry,
            analyzer=RuleAnalyzer(),
            now=lambda: self.now,
        )
        result = agent.run(
            session_id="limit-session",
            message="성남 판교역에서 오늘 21시에 출발해 차로 20분 안에 갈 약국 찾아줘",
        )
        self.assertEqual(result["replan_count"], 1)
        self.assertEqual(len(result["exclusions"]), 2)
        self.assertIn("재계획 상한 1회", result["stop_reason"])

    def test_ambiguous_place_asks_user_before_institution_search(self) -> None:
        registry = FakeRegistry(ambiguous=True)
        agent = PlannerAgent(
            self.settings,
            registry=registry,
            analyzer=RuleAnalyzer(),
            now=lambda: self.now,
        )
        result = agent.run(
            session_id="ambiguous-session",
            message="판교역에서 출발할래",
        )
        self.assertIn("동명 장소", result["clarification"])
        self.assertEqual(registry.calls["search_place"], 1)
        self.assertEqual(registry.calls["search_nearby_institutions"], 0)

    def test_graph_contains_required_execution_nodes(self) -> None:
        agent = PlannerAgent(
            self.settings,
            registry=FakeRegistry(),
            analyzer=RuleAnalyzer(),
            now=lambda: self.now,
        )
        mermaid = agent.graph_mermaid()
        for node in (
            "analyze_request",
            "build_plan",
            "execute_tools",
            "judge_constraints",
            "replan",
            "generate_response",
        ):
            self.assertIn(node, mermaid)


if __name__ == "__main__":
    unittest.main()
