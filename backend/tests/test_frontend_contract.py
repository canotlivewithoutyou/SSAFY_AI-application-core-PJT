"""Static checks that the UI renders recorded events instead of a timer (F3019).

There is no JS test runner in this project; these checks pin the contract
between ``frontend/assets/app.js`` and the backend trace API.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[2] / "frontend" / "assets" / "app.js"


class FrontendTraceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = APP_JS.read_text(encoding="utf-8")

    def test_no_timer_driven_stage_progress(self) -> None:
        self.assertNotIn("setInterval", self.source)
        self.assertNotIn("progressTimer", self.source)

    def test_trace_is_loaded_per_request_id(self) -> None:
        self.assertIn("/logs/sessions/", self.source)
        self.assertRegex(self.source, r"request_id=\$\{encodeURIComponent\(response\.request_id\)\}")
        self.assertIn("trace?.request_id !== response.request_id", self.source)
        self.assertIn("sequence !== requestSequence", self.source)

    def test_trace_kinds_rendered_match_backend_summary(self) -> None:
        backend = (APP_JS.parents[2] / "backend" / "app" / "services" / "trace.py").read_text(
            encoding="utf-8"
        )
        kinds = set(re.findall(r'"kind": "([a-z_]+)"', backend))
        self.assertEqual(
            kinds,
            {"decision", "tool", "candidate_excluded", "candidate_selected", "replan", "setup_required"},
        )
        for kind in kinds:
            self.assertIn(f'case "{kind}"', self.source)

    def test_secret_values_are_never_rendered(self) -> None:
        self.assertIn("missing_settings", self.source)
        for forbidden in ("OPENAI_API_KEY=", "api_key", "innerHTML = `"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
