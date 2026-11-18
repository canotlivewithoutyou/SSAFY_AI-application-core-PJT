from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.app.database import initialize_database
from backend.app.repositories import logs, plans


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


def plan_data(departure_at: datetime) -> dict:
    duration = 600
    return {
        "institution_type": "pharmacy",
        "institution_id": "TEST-H123",
        "institution_name": "테스트약국",
        "institution_address": "경기 성남시 테스트로 1",
        "visit_date": departure_at.date(),
        "origin_name": "성남 판교역 신분당선",
        "origin_longitude": 127.11119782955879,
        "origin_latitude": 37.39477752734142,
        "destination_longitude": 127.115,
        "destination_latitude": 37.397,
        "departure_at": departure_at,
        "expected_arrival_at": departure_at + timedelta(seconds=duration),
        "travel_duration_seconds": duration,
        "operation_start": departure_at.replace(hour=9, minute=0),
        "operation_end": departure_at.replace(hour=23, minute=0),
        "selection_reason": "운영시간 내 도착 예상",
    }


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp.name) / "planner.db"
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_plan_crud_and_overlap_detection(self) -> None:
        first_departure = datetime(2026, 11, 19, 21, 0, tzinfo=SEOUL)
        first = plans.create_plan(self.database_path, plan_data(first_departure))
        second = plans.create_plan(
            self.database_path, plan_data(first_departure + timedelta(minutes=5))
        )

        overlapping = plans.find_overlapping_plan_ids(
            self.database_path,
            visit_date=date(2026, 11, 19),
            departure_at=first_departure + timedelta(minutes=5),
            expected_arrival_at=first_departure + timedelta(minutes=15),
            exclude_plan_id=second["id"],
        )
        self.assertEqual(overlapping, [first["id"]])
        self.assertEqual(len(plans.list_plans(self.database_path)), 2)

        updated = plans.update_plan(
            self.database_path,
            first["id"],
            {"selection_reason": "수정한 선택 근거"},
        )
        self.assertEqual(updated["selection_reason"], "수정한 선택 근거")
        self.assertTrue(plans.delete_plan(self.database_path, first["id"]))
        self.assertIsNone(plans.get_plan(self.database_path, first["id"]))

    def test_log_payload_redacts_secret_like_fields(self) -> None:
        event = logs.record_event(
            self.database_path,
            session_id="session-1",
            event_type="tool.requested",
            stage="route",
            payload={"api_key": "do-not-store", "query": "판교역"},
        )
        self.assertEqual(event["payload"]["api_key"], "[REDACTED]")
        self.assertEqual(event["payload"]["query"], "판교역")
        self.assertEqual(len(logs.list_events(self.database_path)), 1)
        self.assertTrue(logs.delete_event(self.database_path, event["id"]))


if __name__ == "__main__":
    unittest.main()

