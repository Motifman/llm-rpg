"""WorldQueryService をラップしスポットグラフ用スナップショットを DTO に付与する。"""

from __future__ import annotations

import dataclasses
from typing import Any

from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)


class SpotGraphAugmentingWorldQueryService:
    """get_player_current_state のみ拡張し、他メソッドは内側へ委譲する。"""

    def __init__(
        self,
        inner: WorldQueryService,
        spot_graph_builder: SpotGraphCurrentStateBuilder,
    ) -> None:
        self._inner = inner
        self._builder = spot_graph_builder

    def get_player_current_state(self, query: GetPlayerCurrentStateQuery) -> Any:
        dto = self._inner.get_player_current_state(query)
        if dto is None:
            return None
        snap = self._builder.build_snapshot(query.player_id)
        if snap is None:
            return dto
        return dataclasses.replace(dto, spot_graph_snapshot=snap)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
