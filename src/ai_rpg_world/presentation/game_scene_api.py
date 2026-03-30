"""Framework-agnostic presentation facade for scene snapshot and stream access."""

from __future__ import annotations

from typing import List

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneDeltaEventDto,
    GameSceneSnapshotDto,
    WorldSceneSummaryDto,
)
from ai_rpg_world.application.ui.services.game_scene_snapshot_service import (
    GameSceneSnapshotService,
)
from ai_rpg_world.application.ui.services.game_scene_stream_service import (
    GameSceneStreamService,
)


class GameSceneApi:
    """Thin presentation facade that can later be adapted to HTTP / WebSocket."""

    def __init__(
        self,
        snapshot_service: GameSceneSnapshotService,
        stream_service: GameSceneStreamService,
    ) -> None:
        self._snapshot_service = snapshot_service
        self._stream_service = stream_service

    def get_scene_snapshot(self, spot_id: int) -> GameSceneSnapshotDto:
        return self._snapshot_service.get_scene_snapshot(spot_id)

    def get_world_overview(self) -> List[WorldSceneSummaryDto]:
        return self._snapshot_service.get_world_overview()

    def get_scene_events(
        self, *, scene_id: str, last_seen_scene_version: int = -1
    ) -> List[GameSceneDeltaEventDto]:
        return self._stream_service.get_events_since(
            scene_id=scene_id,
            last_seen_scene_version=last_seen_scene_version,
        )

