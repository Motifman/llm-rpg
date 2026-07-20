"""SpotGraphCurrentStateBuilder.build_snapshot が同席 DEAD player の is_dead を
dead_player_checker から nearby_entities に載せることを固定する。

DEAD 表示の render (ui_context) と is_dead フラグ (DTO) は別テストで固定済みだが、
「builder が dead_player_checker を引いて entry.is_dead を立てる配線」自体が
固定されていないと、その代入 (_resolve_is_dead / is_dead=other_is_dead) を消しても
両テストは通り、実 prompt から DEAD 区別だけが黙って消える (codex #758 MEDIUM 1)。
build_snapshot 経由で is_dead 配線を固定する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

ACTING_ID = 1
OTHER_ID = 2
SPOT_A = SpotId(1)


def _player(pid: int) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(pid),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


def _build_builder(dead_checker=None) -> SpotGraphCurrentStateBuilder:
    graph = MagicMock()
    graph.get_entity_spot.return_value = SPOT_A
    node = MagicMock()
    node.name = "広間"
    node.description = ""
    node.atmosphere = None
    node.is_outdoor = False
    graph.get_spot.return_value = node
    presence = MagicMock()
    presence.present_entity_ids = frozenset(
        {EntityId.create(ACTING_ID), EntityId.create(OTHER_ID)}
    )
    graph.presence_at.return_value = presence
    mp = MagicMock()
    mp.present_monster_ids = frozenset()
    graph.monster_presence_at.return_value = mp
    graph.iter_outgoing_connections_from.return_value = []

    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph
    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = None
    players = {ACTING_ID: _player(ACTING_ID), OTHER_ID: _player(OTHER_ID)}
    player_status_repo = MagicMock()
    player_status_repo.find_by_id.side_effect = lambda pid: players.get(pid.value)

    builder = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        entity_name_resolver=lambda eid: {1: "ノア", 2: "リオ"}.get(eid, f"p{eid}"),
    )
    if dead_checker is not None:
        builder.set_dead_player_checker(dead_checker)
    return builder


def _entry_for(snap, entity_id: int):
    return next(e for e in snap.nearby_entities if e.entity_id == entity_id)


class TestBuildSnapshotDeadPlayer:
    """build_snapshot が dead_player_checker を引いて nearby entry.is_dead を立てる。"""

    def test_dead_checker_marks_nearby_entry_is_dead(self) -> None:
        """checker が DEAD と答える同席 player の entry.is_dead が True になる。"""
        builder = _build_builder(dead_checker=lambda pid: pid.value == OTHER_ID)
        snap = builder.build_snapshot(ACTING_ID)
        assert _entry_for(snap, OTHER_ID).is_dead is True

    def test_no_checker_leaves_is_dead_false(self) -> None:
        """checker 未注入なら is_dead は False (導入前と同じ挙動)。"""
        builder = _build_builder(dead_checker=None)
        snap = builder.build_snapshot(ACTING_ID)
        assert _entry_for(snap, OTHER_ID).is_dead is False

    def test_living_player_not_marked_dead(self) -> None:
        """checker が False を返す player は is_dead=False のまま。"""
        builder = _build_builder(dead_checker=lambda pid: False)
        snap = builder.build_snapshot(ACTING_ID)
        assert _entry_for(snap, OTHER_ID).is_dead is False
