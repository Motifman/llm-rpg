"""Services for UI-facing snapshot and overview queries."""

from __future__ import annotations

from typing import List, Optional

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    WorldSceneSummaryDto,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class GameSceneSnapshotService:
    """Returns scene snapshots and a world overview from the current projection state."""

    def __init__(
        self,
        projection: GameSceneProjection,
        *,
        spot_repository: Optional[SpotRepository] = None,
    ) -> None:
        self._projection = projection
        self._spot_repository = spot_repository

    def get_scene_snapshot(self, spot_id: int) -> GameSceneSnapshotDto:
        snapshot = self._projection.get_snapshot(spot_id)
        if self._spot_repository is None:
            return snapshot
        spot = self._spot_repository.find_by_id(SpotId(spot_id))
        if spot is not None:
            snapshot.spot_name = spot.name
        return snapshot

    def get_world_overview(self) -> List[WorldSceneSummaryDto]:
        summaries: List[WorldSceneSummaryDto] = []
        for snapshot in self._projection.list_snapshots():
            summaries.append(
                WorldSceneSummaryDto(
                    spot_id=snapshot.spot_id,
                    scene_id=snapshot.scene_id,
                    spot_name=snapshot.spot_name,
                    actor_count=len(snapshot.actors),
                    monster_count=len(snapshot.monsters),
                    weather_type=snapshot.weather.weather_type if snapshot.weather else None,
                    scene_version=snapshot.scene_version,
                )
            )
        return sorted(summaries, key=lambda x: x.spot_id)
