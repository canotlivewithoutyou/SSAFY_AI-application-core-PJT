from __future__ import annotations

import unittest
from dataclasses import replace

from backend.app.agents.llm import OpenAIAnalyzer
from backend.app.config import get_settings
from backend.app.tools import build_registry


class FakeMessage:
    content = ""
    tool_calls = [{"name": "search_place", "args": {"query": "성남 판교역"}}]


class FakeBoundModel:
    def __init__(self, parent):
        self.parent = parent

    def invoke(self, message):
        self.parent.message = message
        return FakeMessage()


class FakeModel:
    def __init__(self):
        self.tools = None
        self.tool_choice = None
        self.message = None

    def bind_tools(self, tools, tool_choice=None):
        self.tools = tools
        self.tool_choice = tool_choice
        return FakeBoundModel(self)


class LLMToolSelectionTests(unittest.TestCase):
    def test_probe_registers_tool_schemas_and_reports_selected_name(self) -> None:
        settings = replace(
            get_settings(),
            openai_api_key="test-openai",
            openai_model="test-model",
        )
        model = FakeModel()
        analyzer = OpenAIAnalyzer(settings, model=model)
        result = analyzer.probe("성남 판교역에서 출발할래", build_registry(settings))

        self.assertEqual(model.tool_choice, "auto")
        self.assertEqual(len(model.tools), 4)
        self.assertEqual(result["tool_calls"][0]["name"], "search_place")
        search_schema = next(
            item for item in model.tools if item["function"]["name"] == "search_place"
        )
        self.assertIn("출발지", search_schema["function"]["description"])


if __name__ == "__main__":
    unittest.main()
