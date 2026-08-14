"""Persistence functions for execution events.

The logging boundary redacts common secret-bearing keys and credential-like
values as a second line of defense. Callers should still avoid passing raw
upstream requests and responses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from ..database import connect
from ..events import SENSITIVE_FRAGMENTS, sanitize_payload


__all__ = [
    "SENSITIVE_FRAGMENTS",
    "delete_event",
    "get_event",
    "get_session_trace",
    "list_events",
    "record_event",
]

_sanitize = sanitize_payload


def record_event(
    database_path: Path,
    *,
    session_id: str,
    event_type: str,
    stage: str,
    payload: Mapping[str, Any] | None = None,
    duration_ms: int | None = None,
    request_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    payload_json = json.dumps(
        _sanitize(payload or {}), ensure_ascii=False, separators=(",", ":")
    )
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO execution_logs
                (session_id, request_id, event_type, stage, payload_json, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, request_id, event_type, stage, payload_json, duration_ms, created_at),
        )
        row = connection.execute(
            "SELECT * FROM execution_logs WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _decode(row)


def _decode(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["payload"] = json.loads(item.pop("payload_json"))
    item.setdefault("request_id", None)
    return item


def list_events(
    database_path: Path,
    *,
    session_id: str | None = None,
    request_id: str | None = None,
    limit: int = 100,
    order: Literal["asc", "desc"] = "desc",
) -> list[dict[str, Any]]:
    """List events. ``desc`` (newest first) stays the default for compatibility."""

    sql = "SELECT * FROM execution_logs"
    conditions: list[str] = []
    parameters: list[Any] = []
    if session_id:
        conditions.append("session_id = ?")
        parameters.append(session_id)
    if request_id:
        conditions.append("request_id = ?")
        parameters.append(request_id)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id ASC" if order == "asc" else " ORDER BY id DESC"
    sql += " LIMIT ?"
    parameters.append(limit)
    with connect(database_path) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [_decode(row) for row in rows]


def _duration_ms(started_at: str | None, ended_at: str | None) -> int | None:
    try:
        start = datetime.fromisoformat(str(started_at))
        end = datetime.fromisoformat(str(ended_at))
    except ValueError:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def get_session_trace(
    database_path: Path,
    session_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    """Return one session's events in execution order (id ASC).

    ``requests`` lists every request run in the session, oldest first, so the
    latest trace can be told apart from earlier conversation turns. When
    ``request_id`` is given only that run's events are returned.
    """

    with connect(database_path) as connection:
        request_rows = connection.execute(
            """
            SELECT request_id,
                   MIN(id) AS first_id,
                   COUNT(*) AS event_count,
                   MIN(created_at) AS started_at,
                   MAX(created_at) AS ended_at
            FROM execution_logs
            WHERE session_id = ?
            GROUP BY request_id
            ORDER BY first_id ASC
            """,
            (session_id,),
        ).fetchall()
        if not request_rows:
            return None
        sql = "SELECT * FROM execution_logs WHERE session_id = ?"
        parameters: list[Any] = [session_id]
        if request_id:
            sql += " AND request_id = ?"
            parameters.append(request_id)
        rows = connection.execute(sql + " ORDER BY id ASC", parameters).fetchall()

    requests = [
        {
            "request_id": row["request_id"],
            "event_count": row["event_count"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "duration_ms": _duration_ms(row["started_at"], row["ended_at"]),
        }
        for row in request_rows
    ]
    identified = [item["request_id"] for item in requests if item["request_id"]]
    return {
        "session_id": session_id,
        "request_id": request_id,
        "latest_request_id": identified[-1] if identified else None,
        "requests": requests,
        "events": [_decode(row) for row in rows],
    }


def get_event(database_path: Path, event_id: int) -> dict[str, Any] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM execution_logs WHERE id = ?", (event_id,)
        ).fetchone()
    return _decode(row)


def delete_event(database_path: Path, event_id: int) -> bool:
    with connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM execution_logs WHERE id = ?", (event_id,)
        )
    return cursor.rowcount > 0
