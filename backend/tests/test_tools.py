from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend.app.config import get_settings
from backend.app.tools.handlers import ExternalToolHandlers


SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")


class FakeResponse:
    def __init__(self, *, payload=None, text: str = "", status_code: int = 200):
        self.payload = payload
        self.text = text
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self.payload


class RoutingGet:
    def __init__(self, routes):
        self.routes = routes
        self.calls: list[dict] = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        for suffix, response in self.routes:
            if suffix in url:
                return response
        raise AssertionError(f"Unexpected URL: {url}")


class ExternalToolHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = replace(
            get_settings(),
            kakao_rest_api_key="test-kakao",
            nmc_service_key="encoded%2Btest-key",
        )

    def test_place_search_marks_cross_region_name_ambiguous(self) -> None:
        payload = {
            "documents": [
                {
                    "id": "1",
                    "place_name": "판교역 신분당선",
                    "road_address_name": "경기 성남시 분당구 판교역로 160",
                    "x": "127.1111",
                    "y": "37.3947",
                },
                {
                    "id": "2",
                    "place_name": "판교역",
                    "road_address_name": "충남 서천군 판교면 저산길 5",
                    "x": "126.689",
                    "y": "36.153",
                },
            ]
        }
        http = RoutingGet([("keyword.json", FakeResponse(payload=payload))])
        handlers = ExternalToolHandlers(self.settings, http_get=http)

        ambiguous = handlers.search_place(query="판교역")
        resolved = handlers.search_place(query="성남 판교역")

        self.assertTrue(ambiguous.ok)
        self.assertTrue(ambiguous.data["ambiguous"])
        self.assertFalse(resolved.data["ambiguous"])
        self.assertNotIn("test-kakao", str(ambiguous.to_dict()))

    def test_nearby_hpid_is_passed_to_holiday_detail(self) -> None:
        nearby_xml = """
        <response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
          <body><items><item>
            <hpid>A1100141</hpid><dutyName>테스트병원</dutyName>
            <dutyAddr>경기 성남시 분당구 테스트로 1</dutyAddr>
            <longitude>127.11</longitude><latitude>37.39</latitude><distance>0.8</distance>
          </item></items><pageNo>1</pageNo><numOfRows>20</numOfRows><totalCount>1</totalCount></body>
        </response>
        """
        detail_xml = """
        <response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
          <body><items><item>
            <hpid>A1100141</hpid><dutyName>테스트병원</dutyName>
            <dutyAddr>경기 성남시 분당구 테스트로 1</dutyAddr>
            <wgs84Lon>127.11</wgs84Lon><wgs84Lat>37.39</wgs84Lat>
            <dutyTime8s>0900</dutyTime8s><dutyTime8c>1800</dutyTime8c>
          </item></items></body>
        </response>
        """
        http = RoutingGet(
            [
                ("getHsptlMdcncLcinfoInqire", FakeResponse(text=nearby_xml)),
                ("getHsptlBassInfoInqire", FakeResponse(text=detail_xml)),
            ]
        )
        handlers = ExternalToolHandlers(self.settings, http_get=http)

        nearby = handlers.search_nearby_institutions(
            longitude=127.1111,
            latitude=37.3947,
            institution_type="hospital",
        )
        institution_id = nearby.data["candidates"][0]["institution_id"]
        detail = handlers.get_institution_detail(
            institution_id=institution_id,
            institution_type="hospital",
            visit_date="2026-12-25",
        )

        self.assertEqual(institution_id, "A1100141")
        self.assertTrue(detail.ok)
        self.assertEqual(detail.data["institution_id"], institution_id)
        self.assertEqual(detail.data["applied_day_type"], "public_holiday")
        self.assertEqual(detail.data["source_fields"], {"start": "dutyTime8s", "end": "dutyTime8c"})
        self.assertEqual(detail.data["hours_status"], "confirmed")
        detail_call = next(call for call in http.calls if "BassInfo" in call["url"])
        self.assertEqual(detail_call["params"]["HPID"], institution_id)
        self.assertEqual(detail_call["params"]["ServiceKey"], "encoded+test-key")

    def test_empty_holiday_hours_are_check_required(self) -> None:
        detail_xml = """
        <response><header><resultCode>00</resultCode></header><body><items><item>
          <hpid>C123</hpid><dutyName>테스트약국</dutyName>
          <dutyAddr>경기 성남시</dutyAddr><wgs84Lon>127.1</wgs84Lon><wgs84Lat>37.4</wgs84Lat>
        </item></items></body></response>
        """
        http = RoutingGet([("getParmacyBassInfoInqire", FakeResponse(text=detail_xml))])
        handlers = ExternalToolHandlers(self.settings, http_get=http)
        result = handlers.get_institution_detail(
            institution_id="C123",
            institution_type="pharmacy",
            visit_date="2026-12-25",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["hours_status"], "확인 필요")
        self.assertIsNone(result.data["opening_intervals"])

    def test_route_selects_current_and_future_endpoints(self) -> None:
        route_payload = {
            "routes": [
                {
                    "result_code": 0,
                    "result_msg": "길찾기 성공",
                    "summary": {"duration": 185, "distance": 523},
                }
            ]
        }
        http = RoutingGet(
            [
                ("future/directions", FakeResponse(payload=route_payload)),
                ("/directions", FakeResponse(payload=route_payload)),
            ]
        )
        now = datetime(2026, 11, 19, 10, 0, tzinfo=SEOUL)
        handlers = ExternalToolHandlers(self.settings, http_get=http, now=lambda: now)
        coordinates = {
            "origin": {"longitude": 127.11, "latitude": 37.39},
            "destination": {"longitude": 127.12, "latitude": 37.40},
        }

        current = handlers.get_driving_route(
            **coordinates,
            departure_at="2026-11-19T10:00:00+09:00",
        )
        future = handlers.get_driving_route(
            **coordinates,
            departure_at="2026-11-19T11:00:00+09:00",
        )

        self.assertEqual(current.data["mode"], "current")
        self.assertEqual(future.data["mode"], "future")
        self.assertNotIn("departure_time", http.calls[0]["params"])
        self.assertEqual(http.calls[1]["params"]["departure_time"], "202611191100")

    def test_missing_keys_return_failure_envelope(self) -> None:
        handlers = ExternalToolHandlers(
            replace(self.settings, kakao_rest_api_key="", nmc_service_key="")
        )
        place = handlers.search_place(query="판교역")
        nearby = handlers.search_nearby_institutions(
            longitude=127.1,
            latitude=37.4,
            institution_type="pharmacy",
        )
        self.assertFalse(place.ok)
        self.assertEqual(place.error.code, "MISSING_API_KEY")
        self.assertFalse(nearby.ok)
        self.assertEqual(nearby.error.code, "MISSING_API_KEY")


if __name__ == "__main__":
    unittest.main()
