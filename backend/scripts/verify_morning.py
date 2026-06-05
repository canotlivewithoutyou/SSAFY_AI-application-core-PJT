r"""Run the live evidence checks for morning items 02-04.

Usage from the repository root::

    .\.venv\Scripts\python.exe -m backend.scripts.verify_morning

The script prints normalized evidence only. API keys and raw upstream payloads
are never printed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

from backend.app.agents.llm import OpenAIAnalyzer
from backend.app.agents.parsing import SEOUL
from backend.app.config import get_settings
from backend.app.tools import ToolResult, build_registry


def _safe(result: ToolResult) -> dict[str, Any]:
    return result.to_dict()


def _find_holiday_detail(registry, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for candidate in candidates[:10]:
        result = registry.invoke(
            "get_institution_detail",
            {
                "institution_id": candidate["institution_id"],
                "institution_type": candidate["institution_type"],
                "visit_date": "2026-12-25",
                "is_public_holiday": True,
            },
        )
        normalized = _safe(result)
        attempts.append(normalized)
        if result.ok and (result.data or {}).get("hours_status") == "confirmed":
            return {"matched": normalized, "attempt_count": len(attempts)}
    return {
        "matched": None,
        "attempt_count": len(attempts),
        "status": "공휴일 운영시간 확인 필요",
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = get_settings()
    missing = settings.missing_integration_settings()
    if missing:
        print(
            json.dumps(
                {
                    "status": "setup_required",
                    "missing_settings": missing,
                    "next": "실제 값을 .env에 설정한 뒤 서버 또는 이 스크립트를 다시 실행하세요.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    registry = build_registry(settings)
    analyzer = OpenAIAnalyzer(settings)
    report: dict[str, Any] = {
        "verified_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "llm_model": settings.openai_model,
        "llm": {},
        "live_tools": {},
    }

    general = analyzer.probe("안녕하세요. 이 서비스의 목적을 한 문장으로 설명해 주세요.", registry)
    place_selection = analyzer.probe("성남 판교역에서 출발할래", registry)
    report["llm"] = {
        "general_response": general,
        "place_request": place_selection,
        "search_place_selected": any(
            call.get("name") == "search_place"
            for call in place_selection.get("tool_calls", [])
        ),
    }

    place = registry.invoke(
        "search_place",
        {"query": "성남 판교역 신분당선", "region_hint": "성남"},
    )
    report["live_tools"]["place"] = _safe(place)
    if not place.ok:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 1
    origin = (place.data or {})["candidates"][0]

    hospital_list = registry.invoke(
        "search_nearby_institutions",
        {
            "longitude": origin["longitude"],
            "latitude": origin["latitude"],
            "institution_type": "hospital",
            "page": 1,
        },
    )
    report["live_tools"]["hospital_list"] = _safe(hospital_list)
    if hospital_list.ok:
        hospital = (hospital_list.data or {})["candidates"][0]
        hospital_detail = registry.invoke(
            "get_institution_detail",
            {
                "institution_id": hospital["institution_id"],
                "institution_type": "hospital",
                "visit_date": datetime.now(SEOUL).date().isoformat(),
            },
        )
        report["live_tools"]["hospital_detail"] = _safe(hospital_detail)
        report["live_tools"]["hpid_chain_matches"] = bool(
            hospital_detail.ok
            and (hospital_detail.data or {}).get("institution_id")
            == hospital["institution_id"]
        )

        route = registry.invoke(
            "get_driving_route",
            {
                "origin": {
                    "longitude": origin["longitude"],
                    "latitude": origin["latitude"],
                },
                "destination": {
                    "longitude": hospital["longitude"],
                    "latitude": hospital["latitude"],
                },
                "departure_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
            },
        )
        report["live_tools"]["route"] = _safe(route)

    pharmacy_list = registry.invoke(
        "search_nearby_institutions",
        {
            "longitude": origin["longitude"],
            "latitude": origin["latitude"],
            "institution_type": "pharmacy",
            "page": 1,
        },
    )
    report["live_tools"]["pharmacy_list"] = _safe(pharmacy_list)
    holiday_candidates: list[dict[str, Any]] = []
    if hospital_list.ok:
        holiday_candidates.extend((hospital_list.data or {}).get("candidates") or [])
    if pharmacy_list.ok:
        holiday_candidates.extend((pharmacy_list.data or {}).get("candidates") or [])
    report["live_tools"]["public_holiday_detail"] = _find_holiday_detail(
        registry,
        holiday_candidates,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    passed = bool(
        general.get("answer")
        and report["llm"]["search_place_selected"]
        and report["live_tools"].get("hpid_chain_matches")
        and report["live_tools"]["public_holiday_detail"].get("matched")
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
