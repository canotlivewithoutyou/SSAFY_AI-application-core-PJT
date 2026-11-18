"""Persistence functions for execution events.

The logging boundary redacts common secret-bearing keys as a second line of
defense. Callers should still avoid passing raw upstream requests and responses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..database import connect


SENSITIVE_FRAGMENTS = ("authorization", "api_key", "apikey", "token", "secret", "service_key")


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            clean[str(key)] = (
                "[REDACTED]"
                if any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS)
                else _sanitize(item)
            )
        return clean
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record_event(
    database_path: Path,
    *,
    session_id: str,
    event_type: str,
    stage: str,
    payload: Mapping[str, Any] | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    payload_json = json.dumps(
        _sanitize(payload or {}), ensure_ascii=False, separators=(",", ":")
    )
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO execution_logs
                (session_id, event_type, stage, payload_json, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, event_type, stage, payload_json, duration_ms, created_at),
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
    return item


def list_events(
    database_path: Path,
    *,
    session_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM execution_logs"
    parameters: list[Any] = []
    if session_id:
        sql += " WHERE session_id = ?"
        parameters.append(session_id)
    sql += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)
    with connect(database_path) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [_decode(row) for row in rows]


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

