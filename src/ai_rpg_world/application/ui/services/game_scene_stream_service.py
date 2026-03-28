"""Services for scene delta stream consumption."""

from __future__ import annotations

from typing import List

from ai_rpg_world.application.ui.contracts.dtos import GameSceneDeltaEventDto
from ai_rpg_world.application.ui.contracts.interfaces import IGameSceneEventBroker


class GameSceneStreamService:
    """Provides cursor-based access to published scene delta events."""

    def __init__(self, broker: IGameSceneEventBroker) -> None:
        self._broker = broker

    def get_events_since(
        self,
        *,
        scene_id: str,
        last_seen_scene_version: int = -1,
    ) -> List[GameSceneDeltaEventDto]:
        events = self._broker.get_published_events(scene_id=scene_id)
        return [
            event
            for event in events
            if event.scene_version > last_seen_scene_version
        ]

