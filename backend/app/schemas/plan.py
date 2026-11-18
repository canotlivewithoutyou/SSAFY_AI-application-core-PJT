"""Visit-plan API contracts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")
InstitutionType = Literal["hospital", "pharmacy"]


def _as_seoul(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=SEOUL)
    return value.astimezone(SEOUL)


class PlanCreate(BaseModel):
    institution_type: InstitutionType
    institution_id: str | None = Field(default=None, max_length=100)
    institution_name: str = Field(min_length=1, max_length=200)
    institution_address: str = Field(min_length=1, max_length=500)
    visit_date: date
    origin_name: str = Field(min_length=1, max_length=300)
    origin_longitude: float = Field(ge=-180, le=180)
    origin_latitude: float = Field(ge=-90, le=90)
    destination_longitude: float = Field(ge=-180, le=180)
    destination_latitude: float = Field(ge=-90, le=90)
    departure_at: datetime
    expected_arrival_at: datetime
    travel_duration_seconds: int = Field(ge=0)
    operation_start: datetime | None = None
    operation_end: datetime | None = None
    selection_reason: str = Field(min_length=1, max_length=1000)

    @field_validator(
        "departure_at",
        "expected_arrival_at",
        "operation_start",
        "operation_end",
        mode="after",
    )
    @classmethod
    def normalize_korean_time(cls, value: datetime | None) -> datetime | None:
        return _as_seoul(value)

    @model_validator(mode="after")
    def validate_time_relationships(self) -> "PlanCreate":
        calculated = self.departure_at + timedelta(seconds=self.travel_duration_seconds)
        if abs((calculated - self.expected_arrival_at).total_seconds()) > 1:
            raise ValueError("예상 도착 시각은 출발 시각 + 주행시간과 일치해야 합니다.")
        if self.visit_date != self.expected_arrival_at.date():
            raise ValueError("방문 날짜는 한국 표준시 기준 예상 도착 날짜와 같아야 합니다.")
        if (self.operation_start is None) != (self.operation_end is None):
            raise ValueError("운영 시작과 종료 시각은 함께 입력하거나 함께 비워야 합니다.")
        if self.operation_start and self.operation_end:
            if self.operation_end <= self.operation_start:
                raise ValueError("운영 종료 시각은 시작 시각보다 뒤여야 합니다.")
            if not self.operation_start <= self.expected_arrival_at < self.operation_end:
                raise ValueError("예상 도착 시각이 저장할 운영 구간 안에 있어야 합니다.")
        return self


class PlanUpdate(BaseModel):
    institution_type: InstitutionType | None = None
    institution_id: str | None = Field(default=None, max_length=100)
    institution_name: str | None = Field(default=None, min_length=1, max_length=200)
    institution_address: str | None = Field(default=None, min_length=1, max_length=500)
    visit_date: date | None = None
    origin_name: str | None = Field(default=None, min_length=1, max_length=300)
    origin_longitude: float | None = Field(default=None, ge=-180, le=180)
    origin_latitude: float | None = Field(default=None, ge=-90, le=90)
    destination_longitude: float | None = Field(default=None, ge=-180, le=180)
    destination_latitude: float | None = Field(default=None, ge=-90, le=90)
    departure_at: datetime | None = None
    expected_arrival_at: datetime | None = None
    travel_duration_seconds: int | None = Field(default=None, ge=0)
    operation_start: datetime | None = None
    operation_end: datetime | None = None
    selection_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator(
        "departure_at",
        "expected_arrival_at",
        "operation_start",
        "operation_end",
        mode="after",
    )
    @classmethod
    def normalize_korean_time(cls, value: datetime | None) -> datetime | None:
        return _as_seoul(value)


class PlanOut(PlanCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PlanMutationResponse(BaseModel):
    plan: PlanOut
    warnings: list[str] = Field(default_factory=list)
    overlapping_plan_ids: list[int] = Field(default_factory=list)

