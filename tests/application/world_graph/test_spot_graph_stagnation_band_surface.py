"""SpotGraphCurrentStateBuilder が停滞感バンドを snapshot に載せる挙動 (P-U3/P-U4)。

検証対象:
- ``stagnation_band_provider`` を注入すると、行動者本人の
  ``own_stagnation_band`` (P-U3) と、同 spot の他 player の
  ``nearby_entities[].stagnation_band`` (P-U4) の両方に反映される
  (= 1 本の provider を自己・他者が共有する設計)。
- provider 未注入なら常に ``none`` (= 導入前と同じ、何も表出しない)。
- provider が例外を投げても snapshot 生成全体は落ちず、``none`` に縮退する。
- 行動者本人は nearby_entities に出ない (= 自分自身の停滞感が他者欄に混ざらない)。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

SPOT_A = SpotId(1)
PLAYER_ID = 1
OTHER_PLAYER_ID = 2


def _build_graph_mock(*, present_entity_ids: list[int] | None = None):
    """SpotGraphAggregate を装う MagicMock を組み立てる。"""
    graph = MagicMock()
    graph.get_entity_spot.return_value = SPOT_A

    spot_node = MagicMock()
    spot_node.name = "広間"
    spot_node.description = ""
    spot_node.atmosphere = None
    spot_node.is_outdoor = False
    graph.get_spot.return_value = spot_node

    presence = MagicMock()
    presence.present_entity_ids = frozenset(
        EntityId.create(eid) for eid in (present_entity_ids or [])
    )
    graph.presence_at.return_value = presence

    monster_presence = MagicMock()
    monster_presence.present_monster_ids = frozenset()
    graph.monster_presence_at.return_value = monster_presence

    graph.iter_outgoing_connections_from.return_value = []
    return graph


def _build_builder(*, graph, stagnation_band_provider=None):
    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph

    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = None

    player_status_repo = MagicMock()
    # player / 他 player とも None にして needs / fatigue 解決の枝を単純化する。
    player_status_repo.find_by_id.return_value = None

    return SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        stagnation_band_provider=stagnation_band_provider,
    )


class TestOwnStagnationBandSurface:
    """P-U3: 行動者本人の own_stagnation_band が provider から埋まる。"""

    def test_returns_own_stagnation_band_provider_light_when(self) -> None:
        """provider が light を返すと own stagnation band に反映される。"""
        graph = _build_graph_mock()
        builder = _build_builder(
            graph=graph,
            stagnation_band_provider=lambda pid: "light",
        )
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.own_stagnation_band == "light"

    def test_returns_own_stagnation_band_provider_strong_when(self) -> None:
        """provider が strong を返すと own stagnation band に反映される。"""
        graph = _build_graph_mock()
        builder = _build_builder(
            graph=graph,
            stagnation_band_provider=lambda pid: "strong",
        )
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.own_stagnation_band == "strong"

    def test_provider_uninjected_own_stagnation_band_none(self) -> None:
        """provider 未注入なら own stagnation band は none。"""
        graph = _build_graph_mock()
        builder = _build_builder(graph=graph, stagnation_band_provider=None)
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.own_stagnation_band == "none"

    def test_provider_exception_falls_back_to_none_without_failing_snapshot(self) -> None:
        """provider が例外を投げても snapshot生成は落ちず none に縮退する。"""
        def boom(pid: int) -> str:
            raise RuntimeError("store broken")

        graph = _build_graph_mock()
        builder = _build_builder(graph=graph, stagnation_band_provider=boom)
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.own_stagnation_band == "none"

    def test_provider_action_self_player_id(self) -> None:
        """provider には 行動者本人の player id が渡る。"""
        received: list[int] = []

        def capture(pid: int) -> str:
            received.append(pid)
            return "none"

        graph = _build_graph_mock()
        builder = _build_builder(graph=graph, stagnation_band_provider=capture)
        builder.build_snapshot(PLAYER_ID)
        assert received == [PLAYER_ID]


class TestNearbyEntityStagnationBandSurface:
    """P-U4: 同 spot の他 player の stagnation_band が provider から埋まる。"""

    def test_spot_other_player_stagnation_band_strong(self) -> None:
        """同spotの他playerの stagnation band が strong で埋まる。"""
        graph = _build_graph_mock(present_entity_ids=[PLAYER_ID, OTHER_PLAYER_ID])
        builder = _build_builder(
            graph=graph,
            stagnation_band_provider=lambda pid: (
                "strong" if pid == OTHER_PLAYER_ID else "none"
            ),
        )
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert len(snap.nearby_entities) == 1
        assert snap.nearby_entities[0].entity_id == OTHER_PLAYER_ID
        assert snap.nearby_entities[0].stagnation_band == "strong"

    def test_zero_none_nearby_entity_none(self) -> None:
        """カウンタ0相当 none のときは nearby entityも none。"""
        graph = _build_graph_mock(present_entity_ids=[PLAYER_ID, OTHER_PLAYER_ID])
        builder = _build_builder(
            graph=graph,
            stagnation_band_provider=lambda pid: "none",
        )
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.nearby_entities[0].stagnation_band == "none"

    def test_provider_unwired_nearby_entity_stagnation_band_none(self) -> None:
        """provider 未配線なら nearby entityの stagnation bandも none。"""
        graph = _build_graph_mock(present_entity_ids=[PLAYER_ID, OTHER_PLAYER_ID])
        builder = _build_builder(graph=graph, stagnation_band_provider=None)
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.nearby_entities[0].stagnation_band == "none"

    def test_action_self_nearby_entities_not_rendered(self) -> None:
        """自分自身の停滞感が「他者」欄に混ざらないことを確認する。"""
        graph = _build_graph_mock(present_entity_ids=[PLAYER_ID, OTHER_PLAYER_ID])
        builder = _build_builder(
            graph=graph,
            stagnation_band_provider=lambda pid: "strong",
        )
        snap = builder.build_snapshot(PLAYER_ID)
        assert snap is not None
        entity_ids = [e.entity_id for e in snap.nearby_entities]
        assert PLAYER_ID not in entity_ids
        assert entity_ids == [OTHER_PLAYER_ID]
