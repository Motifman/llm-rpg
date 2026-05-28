"""SpotGraphAugmentingWorldQueryService が tile 系フィールドを None に上書きする。

Issue #227 chore (tile-map 依存除去) PR-4:
    spot_graph 経路では tile 由来の current_terrain_type / visible_tile_map は
    意味を持たないため、Augmenting Decorator が常に None で上書きする。
    これにより内部 WorldQueryService が tile データを生成しても、spot_graph 経路の
    プロンプトには tile 由来のノイズが混入しないことを構造的に保証する。
"""

import dataclasses
from typing import Optional
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.application.world_graph.spot_graph_augmenting_world_query import (
    SpotGraphAugmentingWorldQueryService,
)


@dataclasses.dataclass
class _FakeDto:
    """tile フィールドを持つ最小 DTO (PlayerCurrentStateDto のサブセット)。"""

    current_terrain_type: Optional[str] = "ROAD"
    visible_tile_map: Optional[object] = "DUMMY_TILE_MAP"
    spot_graph_snapshot: Optional[object] = None


class TestSpotGraphAugmentingWorldQueryServiceTileFields:
    """Augmenting Decorator は current_terrain_type / visible_tile_map を None に上書きする。"""

    def test_current_terrain_type_is_overwritten_to_none(self) -> None:
        """内部 DTO が terrain_type を持っていても None で上書きされる。"""
        inner = MagicMock()
        inner.get_player_current_state.return_value = _FakeDto()
        builder = MagicMock()
        builder.build_snapshot.return_value = None

        svc = SpotGraphAugmentingWorldQueryService(inner=inner, spot_graph_builder=builder)
        result = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1)
        )
        assert result.current_terrain_type is None

    def test_visible_tile_map_is_overwritten_to_none(self) -> None:
        """内部 DTO が visible_tile_map を持っていても None で上書きされる。"""
        inner = MagicMock()
        inner.get_player_current_state.return_value = _FakeDto()
        builder = MagicMock()
        builder.build_snapshot.return_value = None

        svc = SpotGraphAugmentingWorldQueryService(inner=inner, spot_graph_builder=builder)
        result = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1)
        )
        assert result.visible_tile_map is None

    def test_spot_graph_snapshot_is_added_when_builder_returns_snap(self) -> None:
        """builder が snapshot を返すと spot_graph_snapshot にセットされる。"""
        inner = MagicMock()
        inner.get_player_current_state.return_value = _FakeDto()
        builder = MagicMock()
        builder.build_snapshot.return_value = "SNAP_OBJECT"

        svc = SpotGraphAugmentingWorldQueryService(inner=inner, spot_graph_builder=builder)
        result = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1)
        )
        assert result.spot_graph_snapshot == "SNAP_OBJECT"
        # tile フィールドも合わせて None になる
        assert result.current_terrain_type is None
        assert result.visible_tile_map is None

    def test_returns_none_when_inner_returns_none(self) -> None:
        """内部 DTO が None なら None を返す (未配置プレイヤー想定)。"""
        inner = MagicMock()
        inner.get_player_current_state.return_value = None
        builder = MagicMock()

        svc = SpotGraphAugmentingWorldQueryService(inner=inner, spot_graph_builder=builder)
        result = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1)
        )
        assert result is None
