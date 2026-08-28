"""HUNGER=max での飢餓 HP ダメージ検証 (v2-hunger フェーズ)。

Minecraft 風: HUNGER が limit に達したら毎 tick 1 HP 減る。HP 0 で
PlayerDownedEvent が集約へ積まれ、確定後配送から死亡処理へ連鎖する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.agent_need import NeedType


def _run_rules(stage: SpotGraphNeedsDecayStageService, repo: MagicMock) -> None:
    """確定境界から独立した飢餓規則だけを検証する。"""
    evidence_statuses = stage._run_with_repository(repo)
    stage._sync_hunger_max_evidence_all(evidence_statuses)


def _build_status_with_hunger(hunger_value: int, hp: int = 100) -> PlayerStatusAggregate:
    """指定の HUNGER 値 / HP でプレイヤー status を作る (テスト用 builder)。"""
    from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
    from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
    from ai_rpg_world.domain.player.value_object.gold import Gold
    from ai_rpg_world.domain.player.value_object.growth import Growth
    from ai_rpg_world.domain.player.value_object.hp import Hp
    from ai_rpg_world.domain.player.value_object.mp import Mp
    from ai_rpg_world.domain.player.value_object.player_id import PlayerId
    from ai_rpg_world.domain.player.value_object.stamina import Stamina
    from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
    exp_table = ExpTable(100, 1.5)
    status = PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )
    # 初期 HUNGER を強制設定 (default は 0)
    if hunger_value > 0:
        status.increase_need(NeedType.HUNGER, hunger_value)
    return status


class TestStarvationDamageDisabled:
    """starvation_damage_per_tick=0 (デフォルト) なら既存挙動と同じ。"""

    def test_default_hp(self) -> None:
        """default では HP 減らない。"""
        status = _build_status_with_hunger(hunger_value=100, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService()  # default starvation=0

        _run_rules(stage, repo)

        assert status.hp.value == 100


class TestStarvationDamageEnabled:
    """starvation_damage_per_tick=1 で HUNGER=max のプレイヤーが HP-1/tick。"""

    def test_hunger_max_hp_one_decreases(self) -> None:
        """HUNGER max なら HP 1 減る。"""
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(starvation_damage_per_tick=1)

        # 1 tick: HUNGER 99 → 100, ここで max 到達 → starvation damage 1 適用
        _run_rules(stage, repo)

        assert status.needs.get(NeedType.HUNGER).value == 100
        assert status.hp.value == 99

    def test_hunger_max_below_hp(self) -> None:
        """HUNGER max 未満なら HP 減らない。"""
        status = _build_status_with_hunger(hunger_value=50, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(starvation_damage_per_tick=1)

        _run_rules(stage, repo)

        # HUNGER 50→51、まだ max ではないので HP は減らない
        assert status.hp.value == 100

    def test_hp_zero_player_records_downed_event(self) -> None:
        """飢餓死: HP 1 + HUNGER 100 で 1 tick 走らせると PlayerDownedEvent が
        集約へ積まれ、確定後配送の起点になる。"""
        status = _build_status_with_hunger(hunger_value=100, hp=1)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(
            starvation_damage_per_tick=1,
        )

        _run_rules(stage, repo)

        assert status.hp.value == 0
        assert any(isinstance(event, PlayerDownedEvent) for event in status.get_events())
