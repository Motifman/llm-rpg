"""`SpotGraphCurrentStateBuilder` がモンスター個体を snapshot に載せる挙動。

検証対象:
- `monster_presence_at(spot_id)` で取得した monster_id 集合を view provider で
  解決し、`monsters_at_spot` に並べる
- `monster_view_provider` が None を返した個体は黙って除外される
- 暗闇（`can_see=False`）では完全に隠す（OBJ と同じゲート）
- view provider 未注入では section が空になる（後方互換）
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphMonsterEntry,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


SPOT_A = SpotId(1)
PLAYER_ID = 1


def _build_graph_mock(
    *,
    present_monster_ids: list[MonsterId] | None = None,
    is_outdoor: bool = False,
):
    """SpotGraphAggregate を装う MagicMock を組み立てる。"""
    graph = MagicMock()
    graph.get_entity_spot.return_value = SPOT_A

    spot_node = MagicMock()
    spot_node.name = "森の入口"
    spot_node.description = ""
    spot_node.atmosphere = None  # 知覚補足を発生させないため簡素化
    spot_node.is_outdoor = is_outdoor
    graph.get_spot.return_value = spot_node

    presence = MagicMock()
    presence.present_entity_ids = frozenset()
    graph.presence_at.return_value = presence

    monster_presence = MagicMock()
    monster_presence.present_monster_ids = frozenset(present_monster_ids or [])
    graph.monster_presence_at.return_value = monster_presence

    graph.iter_outgoing_connections_from.return_value = []
    return graph


def _build_builder(
    *,
    graph,
    monster_view_provider=None,
):
    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph

    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = None

    player_status_repo = MagicMock()
    # シンプルに player を None にして needs / spot_navigation_state の枝を回避。
    player_status_repo.find_by_id.return_value = None

    return SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        monster_view_provider=monster_view_provider,
    )


class TestMonsterSectionPopulation:
    """build_snapshot で monsters_at_spot が埋まる。"""

    def test_view_provider_経由で_monsters_at_spot_が埋まる(self) -> None:
        """presence に居る monster_id 全てが view provider で解決され snapshot に載る。"""
        m1 = MonsterId.create(101)
        m2 = MonsterId.create(102)
        graph = _build_graph_mock(present_monster_ids=[m1, m2])

        def provider(mid: MonsterId):
            return SpotGraphMonsterEntry(
                monster_id=mid.value,
                display_name=f"狼{mid.value}",
                behavior_label="落ち着いている",
                health_bucket="healthy",
                is_dead=False,
            )

        builder = _build_builder(graph=graph, monster_view_provider=provider)
        snap = builder.build_snapshot(PLAYER_ID)

        assert snap is not None
        names = sorted(e.display_name for e in snap.monsters_at_spot)
        assert names == ["狼101", "狼102"]

    def test_provider_が_none_を返した個体は除外される(self) -> None:
        """view 解決失敗（aggregate 未存在等）は snapshot から黙って除外。"""
        m1 = MonsterId.create(101)
        m2 = MonsterId.create(102)  # 解決失敗を装う
        graph = _build_graph_mock(present_monster_ids=[m1, m2])

        def provider(mid: MonsterId):
            if mid.value == 102:
                return None
            return SpotGraphMonsterEntry(
                monster_id=mid.value,
                display_name="灰色のオオカミ",
                behavior_label="落ち着いている",
                health_bucket="healthy",
            )

        builder = _build_builder(graph=graph, monster_view_provider=provider)
        snap = builder.build_snapshot(PLAYER_ID)

        assert snap is not None
        assert len(snap.monsters_at_spot) == 1
        assert snap.monsters_at_spot[0].monster_id == 101

    def test_view_provider_未注入では空(self) -> None:
        """resolver を渡していない構成では monsters_at_spot は空（後方互換）。"""
        graph = _build_graph_mock(present_monster_ids=[MonsterId.create(101)])
        builder = _build_builder(graph=graph, monster_view_provider=None)

        snap = builder.build_snapshot(PLAYER_ID)

        assert snap is not None
        assert snap.monsters_at_spot == ()


class TestDarknessHidesMonsters:
    """暗闇（can_see=False）の挙動。"""

    def test_暗闇では_monsters_at_spot_が空になる(self) -> None:
        """spot.atmosphere の lighting が DARK で光源が無い場合、monsters は隠す。"""
        from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
        from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
        from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
            SpotAtmosphere,
        )

        m1 = MonsterId.create(101)
        graph = _build_graph_mock(present_monster_ids=[m1])

        # spot.atmosphere を DARK にして can_see=False を誘発
        spot_node = graph.get_spot.return_value
        spot_node.atmosphere = SpotAtmosphere(
            lighting=LightingEnum.DARK,
            sound_ambient=None,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
        )

        def provider(mid: MonsterId):
            return SpotGraphMonsterEntry(
                monster_id=mid.value,
                display_name="灰色のオオカミ",
                behavior_label="落ち着いている",
                health_bucket="healthy",
            )

        builder = _build_builder(graph=graph, monster_view_provider=provider)
        snap = builder.build_snapshot(PLAYER_ID)

        assert snap is not None
        assert snap.monsters_at_spot == ()
