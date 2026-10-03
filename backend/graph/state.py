from __future__ import annotations
from typing import Any, TypedDict

class TravelState(TypedDict, total=False):
    request: dict[str, Any]
    trip: dict[str, Any]
    issue: str
    agent_events: list[dict[str, str]]
    status: str
