"""Definitions and runtime registry for the four required external API Tools."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from ..config import Settings, get_settings
from .contracts import ToolResult, ToolSpec, failure
from .handlers import ExternalToolHandlers


COMMON_FAILURE_CODES = (
    "INVALID_INPUT",
    "MISSING_API_KEY",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_HTTP_ERROR",
    "UPSTREAM_API_ERROR",
    "INVALID_UPSTREAM_RESPONSE",
    "NO_RESULT",
)


TOOL_SPECS = (
    ToolSpec(
        name="search_place",
        use_when="출발지가 장소명이나 주소로 주어져 좌표가 필요할 때 사용한다.",
        description="장소 후보의 이름, 주소, WGS84 좌표와 동명 장소 여부를 확인한다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "region_hint": {"type": ["string", "null"]},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "query": "string",
            "ambiguous": "boolean",
            "candidates": "PlaceCandidate[]",
        },
        failure_codes=COMMON_FAILURE_CODES,
    ),
    ToolSpec(
        name="search_nearby_institutions",
        use_when="출발 좌표가 확정된 뒤 주변 병원 또는 약국 후보와 hpid가 필요할 때 사용한다.",
        description="국립중앙의료원 위치 조회로 거리순 후보와 기관 ID를 반환한다.",
        parameters={
            "type": "object",
            "properties": {
                "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                "institution_type": {"enum": ["hospital", "pharmacy"]},
                "page": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["longitude", "latitude", "institution_type"],
            "additionalProperties": False,
        },
        output_schema={
            "query_origin": "Coordinate",
            "institution_type": "hospital | pharmacy",
            "candidates": "InstitutionCandidate[] (includes institution_id/hpid)",
            "pagination": "object",
        },
        failure_codes=COMMON_FAILURE_CODES,
    ),
    ToolSpec(
        name="get_institution_detail",
        use_when="후보 목록에서 받은 hpid로 방문일에 적용할 상세 운영시간을 확인할 때 사용한다.",
        description="기관 상세의 좌표와 요일별 또는 공휴일 운영 구간을 반환하며, 빈 시간은 확인 필요로 둔다.",
        parameters={
            "type": "object",
            "properties": {
                "institution_id": {"type": "string", "minLength": 1},
                "institution_type": {"enum": ["hospital", "pharmacy"]},
                "visit_date": {"type": "string", "format": "date"},
                "is_public_holiday": {"type": ["boolean", "null"]},
            },
            "required": ["institution_id", "institution_type", "visit_date"],
            "additionalProperties": False,
        },
        output_schema={
            "institution_id": "string",
            "applied_date": "date",
            "applied_day_type": "string",
            "hours_status": "confirmed | 확인 필요",
            "opening_intervals": "OpeningInterval[] | null",
        },
        failure_codes=COMMON_FAILURE_CODES + ("ID_MISMATCH",),
    ),
    ToolSpec(
        name="get_driving_route",
        use_when="기관의 좌표와 출발 시각이 확정되어 자동차 예상 주행시간이 필요할 때 사용한다.",
        description="즉시 출발은 자동차 길찾기, 지정한 미래 출발은 미래 운행 정보 길찾기를 선택한다.",
        parameters={
            "type": "object",
            "properties": {
                "origin": {
                    "type": "object",
                    "properties": {
                        "longitude": {"type": "number"},
                        "latitude": {"type": "number"},
                    },
                    "required": ["longitude", "latitude"],
                    "additionalProperties": False,
                },
                "destination": {
                    "type": "object",
                    "properties": {
                        "longitude": {"type": "number"},
                        "latitude": {"type": "number"},
                    },
                    "required": ["longitude", "latitude"],
                    "additionalProperties": False,
                },
                "departure_at": {"type": "string", "format": "date-time"},
            },
            "required": ["origin", "destination", "departure_at"],
            "additionalProperties": False,
        },
        output_schema={
            "mode": "current | future",
            "duration_seconds": "integer",
            "distance_meters": "integer | null",
            "departure_at": "date-time",
        },
        failure_codes=COMMON_FAILURE_CODES + ("PAST_DEPARTURE", "ROUTE_UNAVAILABLE"),
    ),
)


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec]) -> None:
        self._specs = {spec.name: spec for spec in specs}

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())

    def catalog(self) -> list[dict[str, Any]]:
        return [spec.public_definition() for spec in self.specs]

    def llm_definitions(self) -> list[dict[str, Any]]:
        return [spec.llm_definition() for spec in self.specs]

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            return failure("UNKNOWN_TOOL", f"등록되지 않은 Tool입니다: {name}")
        return spec.invoke(arguments)


def build_registry(
    settings: Settings,
    *,
    handlers: ExternalToolHandlers | None = None,
) -> ToolRegistry:
    runtime_handlers = handlers or ExternalToolHandlers(settings)
    bound = tuple(
        replace(spec, handler=getattr(runtime_handlers, spec.name)) for spec in TOOL_SPECS
    )
    return ToolRegistry(bound)


def catalog(settings: Settings | None = None) -> list[dict[str, Any]]:
    return build_registry(settings or get_settings()).catalog()
