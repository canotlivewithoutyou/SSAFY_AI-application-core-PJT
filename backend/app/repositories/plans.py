"""Persistence functions for visit plans."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..database import connect


PLAN_FIELDS = (
    "institution_type",
    "institution_id",
    "institution_name",
    "institution_address",
    "visit_date",
    "origin_name",
    "origin_longitude",
    "origin_latitude",
    "destination_longitude",
    "destination_latitude",
    "departure_at",
    "expected_arrival_at",
    "travel_duration_seconds",
    "operation_start",
    "operation_end",
    "selection_reason",
)


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _values(data: Mapping[str, Any], fields: tuple[str, ...] = PLAN_FIELDS) -> dict[str, Any]:
    return {field: _serialize(data[field]) for field in fields if field in data}


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def create_plan(database_path: Path, data: Mapping[str, Any]) -> dict[str, Any]:
    values = _values(data)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values["created_at"] = now
    values["updated_at"] = now
    columns = tuple(values)
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO visit_plans ({', '.join(columns)}) VALUES ({placeholders})"

    with connect(database_path) as connection:
        cursor = connection.execute(sql, tuple(values[column] for column in columns))
        row = connection.execute(
            "SELECT * FROM visit_plans WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_plans(
    database_path: Path,
    *,
    visit_date: date | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM visit_plans"
    parameters: list[Any] = []
    if visit_date is not None:
        sql += " WHERE visit_date = ?"
        parameters.append(visit_date.isoformat())
    sql += " ORDER BY departure_at ASC, id ASC LIMIT ?"
    parameters.append(limit)
    with connect(database_path) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [dict(row) for row in rows]


def get_plan(database_path: Path, plan_id: int) -> dict[str, Any] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM visit_plans WHERE id = ?", (plan_id,)
        ).fetchone()
    return _row(row)


def update_plan(
    database_path: Path,
    plan_id: int,
    changes: Mapping[str, Any],
) -> dict[str, Any] | None:
    values = _values(changes)
    if not values:
        return get_plan(database_path, plan_id)
    values["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assignments = ", ".join(f"{column} = ?" for column in values)
    parameters = [values[column] for column in values]
    parameters.append(plan_id)

    with connect(database_path) as connection:
        cursor = connection.execute(
            f"UPDATE visit_plans SET {assignments} WHERE id = ?", parameters
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT * FROM visit_plans WHERE id = ?", (plan_id,)
        ).fetchone()
    return _row(row)


def delete_plan(database_path: Path, plan_id: int) -> bool:
    with connect(database_path) as connection:
        cursor = connection.execute("DELETE FROM visit_plans WHERE id = ?", (plan_id,))
    return cursor.rowcount > 0


def find_overlapping_plan_ids(
    database_path: Path,
    *,
    visit_date: date,
    departure_at: datetime,
    expected_arrival_at: datetime,
    exclude_plan_id: int | None = None,
) -> list[int]:
    sql = """
        SELECT id
        FROM visit_plans
        WHERE visit_date = ?
          AND departure_at < ?
          AND expected_arrival_at > ?
    """
    parameters: list[Any] = [
        visit_date.isoformat(),
        expected_arrival_at.isoformat(),
        departure_at.isoformat(),
    ]
    if exclude_plan_id is not None:
        sql += " AND id != ?"
        parameters.append(exclude_plan_id)
    sql += " ORDER BY id"
    with connect(database_path) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return [int(row["id"]) for row in rows]

