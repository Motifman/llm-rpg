"""SpotGraphCurrentStateBuilder.build_snapshot が本人の HP を hp_line に載せる。

domain (Hp.describe / compute_hp_delta) と UI 描画は別テストで固定済みだが、
「builder が aggregate から hp_line を生成して DTO に載せる配線」自体が固定
されていないと、その代入を消しても両テストは通り続け、実 prompt から HP 行
だけが黙って消える (codex #757 レビュー MEDIUM)。build_snapshot 経由で
hp_line が値 + 前 turn 増減つきで載ることを固定する。
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

PLAYER_ID = 1
SPOT_A = SpotId(1)


def _make_player(hp: int = 100) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(PLAYER_ID),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


def _build_builder(player: PlayerStatusAggregate) -> SpotGraphCurrentStateBuilder:
    graph = MagicMock()
    graph.get_entity_spot.return_value = SPOT_A
    node = MagicMock()
    node.name = "広間"
    node.description = ""
    node.atmosphere = None
    node.is_outdoor = False
    graph.get_spot.return_value = node
    presence = MagicMock()
    presence.present_entity_ids = frozenset({EntityId.create(PLAYER_ID)})
    graph.presence_at.return_value = presence
    monster_presence = MagicMock()
    monster_presence.present_monster_ids = frozenset()
    graph.monster_presence_at.return_value = monster_presence
    graph.iter_outgoing_connections_from.return_value = []

    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph
    spot_interior_repo = MagicMock()
    spot_interior_repo.find_by_spot_id.return_value = None
    player_status_repo = MagicMock()
    player_status_repo.find_by_id.return_value = player

    return SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
    )


class TestBuildSnapshotHpLine:
    """build_snapshot が本人 aggregate から hp_line を生成して DTO に載せる。"""

    def test_hp_line_reflects_value_and_delta(self) -> None:
        """snapshot 後に 12 被弾すると hp_line は「HP: 消耗（48/100）、前回 -12」。"""
        player = _make_player(hp=100)
        player.apply_damage(40)          # 60
        player.snapshot_hp_for_delta()   # baseline = 60
        player.apply_damage(12)          # 48
        snap = _build_builder(player).build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.hp_line == "HP: 消耗（48/100）、前回 -12"

    def test_hp_line_present_without_prior_snapshot(self) -> None:
        """初回 (snapshot 前) でも HP 値行は出る (delta 併記なし)。"""
        snap = _build_builder(_make_player(hp=100)).build_snapshot(PLAYER_ID)
        assert snap is not None
        assert snap.hp_line == "HP: 良好（100/100）"
