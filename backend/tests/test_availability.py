from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.app.services.availability import (
    DecisionCode,
    OpeningInterval,
    evaluate_visit,
)


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


class AvailabilityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.departure = datetime(2026, 11, 18, 20, 56, tzinfo=SEOUL)
        self.until_21 = [
            OpeningInterval(
                start=datetime(2026, 11, 18, 9, 0, tzinfo=SEOUL),
                end=datetime(2026, 11, 18, 21, 0, tzinfo=SEOUL),
            )
        ]

    def test_one_second_before_close_is_selected(self) -> None:
        decision = evaluate_visit(
            departure_at=self.departure,
            travel_duration_seconds=239,
            max_travel_seconds=1200,
            opening_intervals=self.until_21,
        )
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.code, DecisionCode.SELECTED)
        self.assertEqual(decision.expected_arrival_at.second, 59)
        self.assertEqual(decision.seconds_until_close, 1)

    def test_arrival_exactly_at_close_is_excluded(self) -> None:
        decision = evaluate_visit(
            departure_at=self.departure,
            travel_duration_seconds=240,
            max_travel_seconds=1200,
            opening_intervals=self.until_21,
        )
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.code, DecisionCode.OUTSIDE_OPERATING_HOURS)

    def test_travel_limit_is_inclusive(self) -> None:
        open_until_22 = [
            OpeningInterval(
                start=datetime(2026, 11, 18, 9, 0, tzinfo=SEOUL),
                end=datetime(2026, 11, 18, 22, 0, tzinfo=SEOUL),
            )
        ]
        at_limit = evaluate_visit(
            departure_at=self.departure,
            travel_duration_seconds=1200,
            max_travel_seconds=1200,
            opening_intervals=open_until_22,
        )
        over_limit = evaluate_visit(
            departure_at=self.departure,
            travel_duration_seconds=1201,
            max_travel_seconds=1200,
            opening_intervals=open_until_22,
        )
        self.assertTrue(at_limit.eligible)
        self.assertEqual(over_limit.code, DecisionCode.TRAVEL_LIMIT_EXCEEDED)

    def test_missing_route_and_hours_are_distinct(self) -> None:
        route_missing = evaluate_visit(
            departure_at=self.departure,
            travel_duration_seconds=None,
            max_travel_seconds=1200,
            opening_intervals=self.until_21,
        )
        hours_missing = evaluate_visit(
            departure_at=self.departure,
            travel_duration_seconds=100,
            max_travel_seconds=1200,
            opening_intervals=None,
        )
        self.assertEqual(route_missing.code, DecisionCode.ROUTE_UNAVAILABLE)
        self.assertEqual(hours_missing.code, DecisionCode.OPERATING_HOURS_UNKNOWN)

    def test_explicit_overnight_interval_uses_arrival_date(self) -> None:
        departure = datetime(2026, 11, 18, 23, 58, tzinfo=SEOUL)
        overnight = [
            OpeningInterval(
                start=datetime(2026, 11, 18, 22, 0, tzinfo=SEOUL),
                end=datetime(2026, 11, 19, 2, 0, tzinfo=SEOUL),
            )
        ]
        decision = evaluate_visit(
            departure_at=departure,
            travel_duration_seconds=300,
            max_travel_seconds=1200,
            opening_intervals=overnight,
        )
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.expected_arrival_at.day, 19)
        self.assertEqual(decision.expected_arrival_at.minute, 3)


if __name__ == "__main__":
    unittest.main()

