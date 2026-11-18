"""The four required Tool definitions; handlers are connected on day two."""

from __future__ import annotations

from .contracts import ToolSpec


TOOL_SPECS = (
    ToolSpec(
        name="search_place",
        description="출발지가 장소명이나 주소로 주어졌을 때 좌표와 동명 장소 후보를 확인한다.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "region_hint": {"type": ["string", "null"]},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="search_nearby_institutions",
        description="출발 좌표 주변에서 요청한 병원 또는 약국 후보와 기관 ID를 찾는다.",
        parameters={
            "type": "object",
            "properties": {
                "longitude": {"type": "number"},
                "latitude": {"type": "number"},
                "institution_type": {"enum": ["hospital", "pharmacy"]},
                "page": {"type": "integer", "minimum": 1},
            },
            "required": ["longitude", "latitude", "institution_type"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_institution_detail",
        description="후보 목록의 기관 ID로 방문일에 적용할 상세 운영시간을 확인한다.",
        parameters={
            "type": "object",
            "properties": {
                "institution_id": {"type": "string"},
                "visit_date": {"type": "string", "format": "date"},
            },
            "required": ["institution_id", "visit_date"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_driving_route",
        description="현재 또는 지정한 미래 출발 시각 기준 자동차 경로의 거리와 소요시간을 확인한다.",
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
                },
                "destination": {
                    "type": "object",
                    "properties": {
                        "longitude": {"type": "number"},
                        "latitude": {"type": "number"},
                    },
                    "required": ["longitude", "latitude"],
                },
                "departure_at": {"type": "string", "format": "date-time"},
            },
            "required": ["origin", "destination", "departure_at"],
            "additionalProperties": False,
        },
    ),
)


def catalog() -> list[dict]:
    return [spec.public_definition() for spec in TOOL_SPECS]

