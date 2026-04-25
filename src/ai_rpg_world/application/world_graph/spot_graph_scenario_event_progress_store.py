from __future__ import annotations

from typing import FrozenSet


class InMemorySpotGraphScenarioEventProgressStore:
    """発火済みシナリオイベント ID を保持するインメモリストア。"""

    def __init__(self) -> None:
        self._fired_event_ids: set[str] = set()

    def is_fired(self, event_id: str) -> bool:
        return event_id in self._fired_event_ids

    def mark_fired(self, event_id: str) -> None:
        self._fired_event_ids.add(event_id)

    def as_frozen_set(self) -> FrozenSet[str]:
        return frozenset(self._fired_event_ids)
