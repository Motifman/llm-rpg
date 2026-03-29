"""In-memory broker for UI delta events."""

from __future__ import annotations

import threading
from typing import List, Optional

from ai_rpg_world.application.ui.contracts.dtos import GameSceneDeltaEventDto
from ai_rpg_world.application.ui.contracts.interfaces import IGameSceneEventBroker


class InMemoryGameSceneEventBroker(IGameSceneEventBroker):
    def __init__(self) -> None:
        self._events: List[GameSceneDeltaEventDto] = []
        self._lock = threading.Lock()

    def publish(self, event: GameSceneDeltaEventDto) -> None:
        if not isinstance(event, GameSceneDeltaEventDto):
            raise TypeError("event must be GameSceneDeltaEventDto")
        with self._lock:
            self._events.append(event)

    def get_published_events(
        self, *, scene_id: Optional[str] = None
    ) -> List[GameSceneDeltaEventDto]:
        with self._lock:
            if scene_id is None:
                return list(self._events)
            return [event for event in self._events if event.scene_id == scene_id]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
