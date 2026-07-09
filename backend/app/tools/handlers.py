"""HTTP-backed implementations for F3001-F3004.

Only normalized fields needed by the planner leave this module. Credential
values and raw upstream payloads are deliberately never returned or logged.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import unquote
from xml.etree import ElementTree

import requests

from ..config import Settings
from .contracts import ToolResult, failure, success


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")
KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
KAKAO_ROUTE_BASE_URL = "https://apis-navi.kakaomobility.com/v1"
NMC_HOSPITAL_BASE_URL = (
    "https://apis.data.go.kr/B552657/HsptlAsembySearchService"
)
NMC_PHARMACY_BASE_URL = (
    "https://apis.data.go.kr/B552657/ErmctInsttInfoInqireService"
)

NMC_ENDPOINTS = {
    "hospital": {
        "nearby": "getHsptlMdcncLcinfoInqire",
        "detail": "getHsptlBassInfoInqire",
    },
    "pharmacy": {
        "nearby": "getParmacyLcinfoInqire",
        "detail": "getParmacyBassInfoInqire",
    },
}

# Fixed-date holidays can be determined without guessing lunar or substitute
# holidays. For any other public holiday the caller must explicitly pass
# ``is_public_holiday=True``.
FIXED_KOREAN_HOLIDAYS = {
    (1, 1): "신정",
    (3, 1): "삼일절",
    (5, 5): "어린이날",
    (6, 6): "현충일",
    (8, 15): "광복절",
    (10, 3): "개천절",
    (10, 9): "한글날",
    (12, 25): "성탄절",
}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _number(value: Any, cast: Callable[[Any], Any]) -> Any | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _xml_item(element: ElementTree.Element) -> dict[str, str | None]:
    return {child.tag.split("}")[-1]: _clean_text(child.text) for child in element}


def _parse_xml_response(
    text: str,
) -> tuple[str | None, str | None, list[dict[str, Any]], dict[str, Any]]:
    root = ElementTree.fromstring(text)
    result_code = _clean_text(root.findtext(".//resultCode"))
    result_message = _clean_text(root.findtext(".//resultMsg")) or _clean_text(
        root.findtext(".//resultMag")
    )
    items = [_xml_item(item) for item in root.findall(".//items/item")]
    meta = {
        "page": _number(root.findtext(".//pageNo"), int),
        "page_size": _number(root.findtext(".//numOfRows"), int),
        "total_count": _number(root.findtext(".//totalCount"), int),
    }
    return result_code, result_message, items, meta


def _safe_upstream_message(response: Any) -> str:
    status = getattr(response, "status_code", None)
    suffix = f" (HTTP {status})" if status else ""
    return f"외부 API 요청에 실패했습니다{suffix}."


def _region_key(address: str) -> str:
    parts = address.split()
    return " ".join(parts[:2]) if parts else ""


def _looks_ambiguous(query: str, candidates: list[dict[str, Any]]) -> bool:
    if len(candidates) < 2:
        return False
    regions = {_region_key(str(item.get("address") or "")) for item in candidates}
    regions.discard("")
    if len(regions) <= 1:
        return False
    query_tokens = [token for token in query.replace(",", " ").split() if len(token) >= 2]
    matching_regions = {
        region
        for region in regions
        if any(token in region or region in token for token in query_tokens)
    }
    return len(matching_regions) != 1


def _parse_visit_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_departure(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SEOUL)
    return parsed.astimezone(SEOUL)


def _parse_hhmm(raw: str | None, applied_date: date) -> datetime | None:
    cleaned = "".join(character for character in (raw or "") if character.isdigit())
    if not cleaned:
        return None
    cleaned = cleaned.zfill(4)
    try:
        hour = int(cleaned[:-2])
        minute = int(cleaned[-2:])
        if hour == 24 and minute == 0:
            return datetime.combine(applied_date + timedelta(days=1), time.min, SEOUL)
        return datetime.combine(applied_date, time(hour=hour, minute=minute), SEOUL)
    except ValueError:
        return None


class ExternalToolHandlers:
    """Concrete handlers with an injectable HTTP function and clock for tests."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_get: Callable[..., Any] = requests.get,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.http_get = http_get
        self.now = now or (lambda: datetime.now(SEOUL))

    def _json_get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, Any],
    ) -> tuple[dict[str, Any] | None, ToolResult | None]:
        try:
            response = self.http_get(
                url,
                headers=dict(headers),
                params=dict(params),
                timeout=self.settings.upstream_timeout_seconds,
            )
        except requests.Timeout:
            return None, failure("UPSTREAM_TIMEOUT", "외부 API 응답 시간이 초과됐습니다.")
        except requests.RequestException:
            return None, failure("UPSTREAM_UNAVAILABLE", "외부 API에 연결할 수 없습니다.")
        if not getattr(response, "ok", False):
            return None, failure("UPSTREAM_HTTP_ERROR", _safe_upstream_message(response))
        try:
            payload = response.json()
        except (TypeError, ValueError):
            return None, failure("INVALID_UPSTREAM_RESPONSE", "외부 API 응답을 해석할 수 없습니다.")
        if not isinstance(payload, dict):
            return None, failure("INVALID_UPSTREAM_RESPONSE", "외부 API 응답 형식이 올바르지 않습니다.")
        return payload, None

    def _xml_get(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None, ToolResult | None]:
        try:
            response = self.http_get(
                url,
                params=dict(params),
                timeout=self.settings.upstream_timeout_seconds,
            )
        except requests.Timeout:
            return None, None, failure("UPSTREAM_TIMEOUT", "의료기관 API 응답 시간이 초과됐습니다.")
        except requests.RequestException:
            return None, None, failure("UPSTREAM_UNAVAILABLE", "의료기관 API에 연결할 수 없습니다.")
        if not getattr(response, "ok", False):
            return None, None, failure("UPSTREAM_HTTP_ERROR", _safe_upstream_message(response))
        try:
            result_code, result_message, items, meta = _parse_xml_response(response.text)
        except (ElementTree.ParseError, TypeError, ValueError):
            return None, None, failure("INVALID_UPSTREAM_RESPONSE", "의료기관 API 응답을 해석할 수 없습니다.")
        if result_code not in {None, "0", "00"}:
            return None, None, failure(
                "UPSTREAM_API_ERROR",
                f"의료기관 API가 요청을 처리하지 못했습니다 ({result_code}: {result_message or '원인 미제공'}).",
            )
        return items, meta, None

    def search_place(
        self,
        *,
        query: str,
        region_hint: str | None = None,
    ) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return failure("INVALID_INPUT", "검색할 장소명을 입력해 주세요.")
        if not self.settings.kakao_rest_api_key:
            return failure("MISSING_API_KEY", "KAKAO_REST_API_KEY 설정이 필요합니다.")

        search_query = query
        if region_hint and region_hint.strip() and region_hint.strip() not in query:
            search_query = f"{region_hint.strip()} {query}"
        payload, error = self._json_get(
            KAKAO_LOCAL_URL,
            headers={"Authorization": f"KakaoAK {self.settings.kakao_rest_api_key}"},
            params={"query": search_query, "size": 10},
        )
        if error:
            return error
        documents = payload.get("documents", []) if payload else []
        candidates: list[dict[str, Any]] = []
        for document in documents if isinstance(documents, list) else []:
            longitude = _number(document.get("x"), float)
            latitude = _number(document.get("y"), float)
            if longitude is None or latitude is None:
                continue
            candidates.append(
                {
                    "place_id": str(document.get("id") or ""),
                    "name": str(document.get("place_name") or "").strip(),
                    "address": str(
                        document.get("road_address_name")
                        or document.get("address_name")
                        or ""
                    ).strip(),
                    "longitude": longitude,
                    "latitude": latitude,
                    "category": str(document.get("category_name") or "").strip(),
                    "phone": str(document.get("phone") or "").strip() or None,
                    "place_url": str(document.get("place_url") or "").strip() or None,
                }
            )
        if not candidates:
            return failure("NO_RESULT", "일치하는 장소를 찾지 못했습니다.")

        return success(
            {
                "query": query,
                "resolved_query": search_query,
                "ambiguous": _looks_ambiguous(query, candidates),
                "candidates": candidates,
                "source": "Kakao Local keyword search",
            }
        )

    def search_nearby_institutions(
        self,
        *,
        longitude: float,
        latitude: float,
        institution_type: str,
        page: int = 1,
    ) -> ToolResult:
        if institution_type not in NMC_ENDPOINTS:
            return failure("INVALID_INPUT", "기관 종류는 hospital 또는 pharmacy여야 합니다.")
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90) or page < 1:
            return failure("INVALID_INPUT", "좌표 또는 페이지 값이 올바르지 않습니다.")
        if not self.settings.nmc_service_key:
            return failure("MISSING_API_KEY", "NMC_SERVICE_KEY 설정이 필요합니다.")

        base_url = NMC_HOSPITAL_BASE_URL if institution_type == "hospital" else NMC_PHARMACY_BASE_URL
        endpoint = NMC_ENDPOINTS[institution_type]["nearby"]
        items, meta, error = self._xml_get(
            f"{base_url}/{endpoint}",
            params={
                "ServiceKey": unquote(self.settings.nmc_service_key),
                "WGS84_LON": longitude,
                "WGS84_LAT": latitude,
                "pageNo": page,
                "numOfRows": 20,
            },
        )
        if error:
            return error
        candidates: list[dict[str, Any]] = []
        for item in items or []:
            institution_id = _clean_text(item.get("hpid"))
            item_longitude = _number(item.get("longitude") or item.get("wgs84Lon"), float)
            item_latitude = _number(item.get("latitude") or item.get("wgs84Lat"), float)
            if not institution_id or item_longitude is None or item_latitude is None:
                continue
            candidates.append(
                {
                    "institution_id": institution_id,
                    "institution_type": institution_type,
                    "name": _clean_text(item.get("dutyName")) or "이름 확인 필요",
                    "address": _clean_text(item.get("dutyAddr")) or "주소 확인 필요",
                    "longitude": item_longitude,
                    "latitude": item_latitude,
                    "distance_km": _number(item.get("distance"), float),
                    "list_start_time": _clean_text(item.get("startTime")),
                    "list_end_time": _clean_text(item.get("endTime")),
                }
            )
        if not candidates:
            return failure("NO_RESULT", "주변에서 좌표와 기관 ID가 확인되는 후보를 찾지 못했습니다.")
        return success(
            {
                "query_origin": {"longitude": longitude, "latitude": latitude},
                "institution_type": institution_type,
                "page": page,
                "candidates": candidates,
                "pagination": meta or {},
                "source": (
                    "NMC nationwide hospital/clinic location lookup"
                    if institution_type == "hospital"
                    else "NMC nationwide pharmacy location lookup"
                ),
            }
        )

    def get_institution_detail(
        self,
        *,
        institution_id: str,
        institution_type: str,
        visit_date: str,
        is_public_holiday: bool | None = None,
    ) -> ToolResult:
        institution_id = (institution_id or "").strip()
        applied_date = _parse_visit_date(visit_date)
        if not institution_id or institution_type not in NMC_ENDPOINTS or applied_date is None:
            return failure("INVALID_INPUT", "기관 ID, 기관 종류, 방문일을 올바르게 입력해 주세요.")
        if not self.settings.nmc_service_key:
            return failure("MISSING_API_KEY", "NMC_SERVICE_KEY 설정이 필요합니다.")

        fixed_holiday_name = FIXED_KOREAN_HOLIDAYS.get(
            (applied_date.month, applied_date.day)
        )
        holiday = bool(is_public_holiday) if is_public_holiday is not None else bool(fixed_holiday_name)
        day_number = 8 if holiday else applied_date.isoweekday()
        base_url = NMC_HOSPITAL_BASE_URL if institution_type == "hospital" else NMC_PHARMACY_BASE_URL
        endpoint = NMC_ENDPOINTS[institution_type]["detail"]
        items, _, error = self._xml_get(
            f"{base_url}/{endpoint}",
            params={
                "ServiceKey": unquote(self.settings.nmc_service_key),
                "HPID": institution_id,
                "pageNo": 1,
                "numOfRows": 10,
            },
        )
        if error:
            return error
        matching = next(
            (
                item
                for item in (items or [])
                if str(item.get("hpid") or "").strip() == institution_id
            ),
            None,
        )
        if matching is None:
            return failure("ID_MISMATCH", "목록의 기관 ID와 일치하는 상세 정보를 찾지 못했습니다.")

        start_field = f"dutyTime{day_number}s"
        end_field = f"dutyTime{day_number}c"
        start_at = _parse_hhmm(_clean_text(matching.get(start_field)), applied_date)
        end_at = _parse_hhmm(_clean_text(matching.get(end_field)), applied_date)
        intervals: list[dict[str, str]] | None = None
        hours_status = "확인 필요"
        if start_at and end_at:
            if end_at <= start_at:
                end_at += timedelta(days=1)
            intervals = [{"start": start_at.isoformat(), "end": end_at.isoformat()}]
            hours_status = "confirmed"

        return success(
            {
                "institution_id": institution_id,
                "institution_type": institution_type,
                "name": _clean_text(matching.get("dutyName")) or "이름 확인 필요",
                "address": _clean_text(matching.get("dutyAddr")) or "주소 확인 필요",
                "phone": _clean_text(matching.get("dutyTel1")),
                "longitude": _number(matching.get("wgs84Lon"), float),
                "latitude": _number(matching.get("wgs84Lat"), float),
                "applied_date": applied_date.isoformat(),
                "applied_day_type": "public_holiday" if holiday else f"weekday_{day_number}",
                "holiday_name": fixed_holiday_name,
                "holiday_basis": (
                    "explicit"
                    if is_public_holiday is not None
                    else ("fixed_date" if fixed_holiday_name else "weekday_only")
                ),
                "hours_status": hours_status,
                "opening_intervals": intervals,
                "source_fields": {"start": start_field, "end": end_field},
                "source": (
                    "NMC nationwide hospital/clinic detail lookup"
                    if institution_type == "hospital"
                    else "NMC nationwide pharmacy detail lookup"
                ),
            }
        )

    def get_driving_route(
        self,
        *,
        origin: Mapping[str, float],
        destination: Mapping[str, float],
        departure_at: str,
    ) -> ToolResult:
        if not self.settings.kakao_rest_api_key:
            return failure("MISSING_API_KEY", "KAKAO_REST_API_KEY 설정이 필요합니다.")
        departure = _parse_departure(departure_at)
        try:
            origin_longitude = float(origin["longitude"])
            origin_latitude = float(origin["latitude"])
            destination_longitude = float(destination["longitude"])
            destination_latitude = float(destination["latitude"])
        except (KeyError, TypeError, ValueError):
            return failure("INVALID_INPUT", "출발지와 목적지 좌표가 올바르지 않습니다.")
        if departure is None:
            return failure("INVALID_INPUT", "출발 시각은 ISO 8601 형식이어야 합니다.")

        current = self.now().astimezone(SEOUL)
        if departure < current - timedelta(minutes=1):
            return failure("PAST_DEPARTURE", "과거 출발 시각으로는 실시간 경로를 조회할 수 없습니다.")
        # A timestamp effectively equal to ``now`` means immediate departure.
        # Any clearly future timestamp must use Kakao's future-directions API.
        use_future = departure > current + timedelta(seconds=30)
        endpoint = "future/directions" if use_future else "directions"
        params: dict[str, Any] = {
            "origin": f"{origin_longitude},{origin_latitude}",
            "destination": f"{destination_longitude},{destination_latitude}",
            "priority": "RECOMMEND",
            "summary": "true",
        }
        if use_future:
            params["departure_time"] = departure.strftime("%Y%m%d%H%M")
        payload, error = self._json_get(
            f"{KAKAO_ROUTE_BASE_URL}/{endpoint}",
            headers={
                "Authorization": f"KakaoAK {self.settings.kakao_rest_api_key}",
                "Content-Type": "application/json",
            },
            params=params,
        )
        if error:
            return error
        routes = payload.get("routes", []) if payload else []
        route = routes[0] if isinstance(routes, list) and routes else None
        if not isinstance(route, dict):
            return failure("ROUTE_UNAVAILABLE", "차량 경로 결과가 없습니다.")
        result_code = _number(route.get("result_code"), int)
        if result_code != 0:
            return failure(
                "ROUTE_UNAVAILABLE",
                f"차량 경로를 확인할 수 없습니다 (경로 코드 {result_code if result_code is not None else '미제공'}).",
            )
        summary = route.get("summary") if isinstance(route.get("summary"), dict) else {}
        duration = _number(summary.get("duration"), int)
        distance = _number(summary.get("distance"), int)
        if duration is None:
            return failure("ROUTE_UNAVAILABLE", "차량 경로에 예상 주행시간이 없습니다.")
        return success(
            {
                "mode": "future" if use_future else "current",
                "departure_at": departure.isoformat(),
                "duration_seconds": duration,
                "distance_meters": distance,
                "upstream_result_code": result_code,
                "source": (
                    "Kakao Mobility future directions"
                    if use_future
                    else "Kakao Mobility directions"
                ),
            }
        )
