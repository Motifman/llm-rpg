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
        # Issue #227 PR-4 (tile-map 除去): spot_graph 経路では tile 由来の
        # current_terrain_type / visible_tile_map は意味を持たないので
        # 常に None に上書きする。これによりプロンプトに tile 由来の
        # ノイズが混入しないことを構造的に保証する (include_tile_map=False で
        # 既に visible_tile_map=None になっているはずだが、defense in depth)。
        replacements: dict = {
            "current_terrain_type": None,
            "visible_tile_map": None,
        }
        if snap is not None:
            replacements["spot_graph_snapshot"] = snap
        return dataclasses.replace(dto, **replacements)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
