"""HUNGER=max での飢餓 HP ダメージ検証 (v2-hunger フェーズ)。

Minecraft 風: HUNGER が limit に達したら毎 tick 1 HP 減る。HP 0 で
PlayerDownedEvent が積まれ、publisher 経由で DEAD outcome に連鎖する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.agent_need import NeedType


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
        stage = SpotGraphNeedsDecayStageService(repo)  # default starvation=0

        stage.run(WorldTick(1))

        assert status.hp.value == 100


class TestStarvationDamageEnabled:
    """starvation_damage_per_tick=1 で HUNGER=max のプレイヤーが HP-1/tick。"""

    def test_hunger_max_hp_one_decreases(self) -> None:
        """HUNGER max なら HP 1 減る。"""
        status = _build_status_with_hunger(hunger_value=99, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(repo, starvation_damage_per_tick=1)

        # 1 tick: HUNGER 99 → 100, ここで max 到達 → starvation damage 1 適用
        stage.run(WorldTick(1))

        assert status.needs.get(NeedType.HUNGER).value == 100
        assert status.hp.value == 99

    def test_hunger_max_below_hp(self) -> None:
        """HUNGER max 未満なら HP 減らない。"""
        status = _build_status_with_hunger(hunger_value=50, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(repo, starvation_damage_per_tick=1)

        stage.run(WorldTick(1))

        # HUNGER 50→51、まだ max ではないので HP は減らない
        assert status.hp.value == 100

    def test_hp_zero_player_downed_event_publish(self) -> None:
        """飢餓死: HP 1 + HUNGER 100 で 1 tick 走らせると PlayerDownedEvent が
        publisher.publish_all に乗る → DEAD outcome 連鎖の起点になる。"""
        status = _build_status_with_hunger(hunger_value=100, hp=1)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        publisher = MagicMock()
        stage = SpotGraphNeedsDecayStageService(
            repo, starvation_damage_per_tick=1, event_publisher=publisher,
        )

        stage.run(WorldTick(1))

        assert status.hp.value == 0
        # PlayerDownedEvent が publish_all 経由で流れている
        publisher.publish_all.assert_called_once()
        published = publisher.publish_all.call_args[0][0]
        assert any(isinstance(ev, PlayerDownedEvent) for ev in published)


class TestSetterInjection:
    """publisher を後付け注入できる (runtime 順序依存解消用)。"""

    def test_set_event_publisher_after_bind(self) -> None:
        """seteventpublisher で後付け bind できる。"""
        status = _build_status_with_hunger(hunger_value=100, hp=10)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(repo, starvation_damage_per_tick=1)

        # 最初は publisher なしで構築
        assert stage._event_publisher is None

        publisher = MagicMock()
        stage.set_event_publisher(publisher)
        stage.run(WorldTick(1))

        # damage は適用される (HP 10→9)
        assert status.hp.value == 9
        # ただし HP > 0 なので PlayerDownedEvent は積まれない → publish_all は呼ばれない
        publisher.publish_all.assert_not_called()
