"""Pure arrival/operating-hours decision logic.

This module deliberately has no network or database dependency, so the boundary
cases from the validation document can be replayed exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Sequence


class DecisionCode(StrEnum):
    SELECTED = "selected"
    ROUTE_UNAVAILABLE = "route_unavailable"
    TRAVEL_LIMIT_EXCEEDED = "travel_limit_exceeded"
    OPERATING_HOURS_UNKNOWN = "operating_hours_unknown"
    OUTSIDE_OPERATING_HOURS = "outside_operating_hours"


@dataclass(frozen=True, slots=True)
class OpeningInterval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("운영 구간에는 시간대 정보가 필요합니다.")
        if self.end <= self.start:
            raise ValueError("운영 종료 시각은 시작 시각보다 뒤여야 합니다.")


@dataclass(frozen=True, slots=True)
class VisitDecision:
    eligible: bool
    code: DecisionCode
    reason: str
    expected_arrival_at: datetime | None
    seconds_until_close: int | None = None


def evaluate_visit(
    *,
    departure_at: datetime,
    travel_duration_seconds: int | None,
    max_travel_seconds: int,
    opening_intervals: Sequence[OpeningInterval] | None,
) -> VisitDecision:
    """Evaluate one candidate using the documented inclusive/exclusive rules.

    ``opening_intervals=None`` means the data is unknown. An empty sequence means
    operating-hours data was checked and no open interval applies.
    """

    if departure_at.tzinfo is None:
        raise ValueError("출발 시각에는 시간대 정보가 필요합니다.")
    if max_travel_seconds < 0:
        raise ValueError("최대 이동시간은 0 이상이어야 합니다.")
    if travel_duration_seconds is None:
        return VisitDecision(
            eligible=False,
            code=DecisionCode.ROUTE_UNAVAILABLE,
            reason="차량 경로의 이동시간을 확인할 수 없습니다.",
            expected_arrival_at=None,
        )
    if travel_duration_seconds < 0:
        raise ValueError("주행시간은 0 이상이어야 합니다.")

    arrival_at = departure_at + timedelta(seconds=travel_duration_seconds)
    if travel_duration_seconds > max_travel_seconds:
        return VisitDecision(
            eligible=False,
            code=DecisionCode.TRAVEL_LIMIT_EXCEEDED,
            reason="예상 주행시간이 사용자가 정한 이동시간 상한을 초과합니다.",
            expected_arrival_at=arrival_at,
        )
    if opening_intervals is None:
        return VisitDecision(
            eligible=False,
            code=DecisionCode.OPERATING_HOURS_UNKNOWN,
            reason="방문일의 운영시간을 확인할 수 없어 운영 여부 확인이 필요합니다.",
            expected_arrival_at=arrival_at,
        )

    active_interval = next(
        (
            interval
            for interval in opening_intervals
            if interval.start <= arrival_at < interval.end
        ),
        None,
    )
    if active_interval is None:
        return VisitDecision(
            eligible=False,
            code=DecisionCode.OUTSIDE_OPERATING_HOURS,
            reason="예상 도착 시각이 확인된 운영 구간 밖입니다.",
            expected_arrival_at=arrival_at,
        )

    seconds_until_close = int((active_interval.end - arrival_at).total_seconds())
    return VisitDecision(
        eligible=True,
        code=DecisionCode.SELECTED,
        reason="이동시간 상한 이내이며 운영 종료 전에 도착할 것으로 예상됩니다.",
        expected_arrival_at=arrival_at,
        seconds_until_close=seconds_until_close,
    )

