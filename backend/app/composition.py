"""Composition root: wires the event bus, its subscribers and the planner.

This is the only place that knows both the publisher (planner, chat service)
and the subscriber (Logging Agent). Swapping or removing a subscriber is a
change here only.
"""

from __future__ import annotations

from functools import lru_cache

from .agents.logging_agent import subscribe_logging_agent
from .agents.planner import PlannerAgent
from .config import Settings
from .events import EventBus


@lru_cache(maxsize=4)
def get_event_bus(settings: Settings) -> EventBus:
    bus = EventBus()
    subscribe_logging_agent(bus, settings.database_path)
    return bus


@lru_cache(maxsize=4)
def get_planner_agent(settings: Settings) -> PlannerAgent:
    return PlannerAgent(settings, publisher=get_event_bus(settings))
