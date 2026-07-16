"""Deterministic extraction used alongside the LLM analysis result.

Rules cover safety-critical numeric and temporal fields so a model omission does
not silently invent a value. The LLM may fill natural-language gaps, while an
explicit value in the user's latest message always wins.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


def _origin_query(message: str) -> str | None:
    # The origin is the phrase before the first locative ``에서``. Do not try
    # to infer an origin from the verb ``출발하면`` in a follow-up question.
    match = re.search(r"^\s*(.+?)에서(?:\s|$)", message)
    if not match:
        match = re.search(r"출발지(?:는|가|은)?\s*[:=]?\s*([^,.!?]+)", message)
    if not match:
        return None
    value = match.group(1).strip(" ,.!?\"'“”")
    value = re.sub(r"^(?:나는|저는|제가|우리)\s+", "", value)
    value = re.sub(r"^(?:출발지는?|장소는?)\s*", "", value)
    return value or None


def _explicit_date(message: str, now: datetime) -> date | None:
    if "모레" in message:
        return (now + timedelta(days=2)).date()
    if "내일" in message:
        return (now + timedelta(days=1)).date()
    if "오늘" in message or "지금" in message or "즉시" in message:
        return now.date()
    iso_match = re.search(r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?", message)
    if iso_match:
        try:
            return date(*(int(part) for part in iso_match.groups()))
        except ValueError:
            return None
    month_day = re.search(r"(?<!\d)(\d{1,2})월\s*(\d{1,2})일", message)
    if month_day:
        try:
            return date(now.year, int(month_day.group(1)), int(month_day.group(2)))
        except ValueError:
            return None
    return None


def _explicit_time(message: str) -> time | None:
    match = re.search(
        r"(?:(오전|오후|밤|새벽)\s*)?(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?",
        message,
    )
    if not match:
        colon = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", message)
        if not colon:
            return None
        return time(int(colon.group(1)), int(colon.group(2)))
    qualifier, raw_hour, raw_minute = match.groups()
    hour = int(raw_hour)
    minute = int(raw_minute or 0)
    if qualifier in {"오후", "밤"} and hour < 12:
        hour += 12
    if qualifier == "새벽" and hour == 12:
        hour = 0
    if qualifier == "오전" and hour == 12:
        hour = 0
    try:
        return time(hour, minute)
    except ValueError:
        return None


def _previous_departure(previous: Mapping[str, Any]) -> datetime | None:
    value = previous.get("departure_at")
    if isinstance(value, datetime):
        return value.astimezone(SEOUL) if value.tzinfo else value.replace(tzinfo=SEOUL)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(SEOUL) if parsed.tzinfo else parsed.replace(tzinfo=SEOUL)
    return None


def extract_explicit_fields(
    message: str,
    *,
    previous: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Extract fields explicitly present in the latest message.

    Missing fields are omitted, allowing the caller to preserve the previous
    session context without confusing omission with deletion.
    """

    current = (now or datetime.now(SEOUL)).astimezone(SEOUL)
    prior = previous or {}
    fields: dict[str, Any] = {}
    origin = _origin_query(message)
    if origin and "같은 곳" not in origin:
        fields["origin_query"] = origin

    if "약국" in message:
        fields["institution_type"] = "pharmacy"
    elif re.search(r"병원|병[·ㆍ]?의원|의원", message):
        fields["institution_type"] = "hospital"

    travel_match = re.search(r"(\d{1,3})\s*분\s*(?:안|이내)", message)
    if travel_match:
        fields["max_travel_seconds"] = int(travel_match.group(1)) * 60

    offset_match = re.search(r"(\d{1,3})\s*분\s*(?:뒤|후)", message)
    if offset_match:
        base = _previous_departure(prior) or current
        fields["departure_at"] = base + timedelta(minutes=int(offset_match.group(1)))
    elif re.search(r"지금|바로|즉시", message):
        fields["departure_at"] = current.replace(microsecond=0)
    else:
        explicit_time = _explicit_time(message)
        if explicit_time is not None:
            explicit_date = _explicit_date(message, current) or current.date()
            fields["departure_at"] = datetime.combine(explicit_date, explicit_time, SEOUL)
        else:
            explicit_date = _explicit_date(message, current)
            previous_departure = _previous_departure(prior)
            if explicit_date is not None and previous_departure is not None:
                fields["departure_at"] = datetime.combine(
                    explicit_date,
                    previous_departure.timetz().replace(tzinfo=None),
                    SEOUL,
                )

    if "공휴일" in message:
        fields["is_public_holiday"] = True
    return fields


def normalize_llm_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize optional structured LLM output without accepting bad values."""

    normalized: dict[str, Any] = {}
    for key in ("origin_query", "institution_type", "is_public_holiday"):
        value = raw.get(key)
        if value is not None:
            normalized[key] = value
    minutes = raw.get("max_travel_minutes")
    if isinstance(minutes, int) and 0 < minutes <= 180:
        normalized["max_travel_seconds"] = minutes * 60
    departure = raw.get("departure_at")
    if isinstance(departure, str):
        try:
            parsed = datetime.fromisoformat(departure.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            normalized["departure_at"] = (
                parsed.astimezone(SEOUL) if parsed.tzinfo else parsed.replace(tzinfo=SEOUL)
            )
    return normalized
