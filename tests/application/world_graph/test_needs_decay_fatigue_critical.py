"""PR β: 疲労限界 (FATIGUE >= threshold) で毎 tick HP を微減させる検証。

starvation と同型のメカニクス。default は無効 (= 後方互換) で、
``fatigue_critical_damage_per_tick > 0`` を渡したシナリオだけで発動する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


def _build_status(fatigue_value: int, hp: int = 100) -> PlayerStatusAggregate:
    """指定 FATIGUE / HP で status を組み立てる test 用 builder。"""
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
    if fatigue_value > 0:
        status.increase_need(NeedType.FATIGUE, fatigue_value)
    return status


class TestFatigueCriticalDamageDisabled:
    """``fatigue_critical_damage_per_tick=0`` (default) は HP に影響しない。"""

    def test_default_hp(self) -> None:
        """旧シナリオ (脱出ゲーム等) の挙動は完全に不変であること。"""
        status = _build_status(fatigue_value=100, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(repo)

        stage.run(WorldTick(1))

        assert status.hp.value == 100


class TestFatigueCriticalDamageEnabled:
    """``fatigue_critical_damage_per_tick=1`` で threshold 超過時に HP-1/tick。"""

    def test_fatigue_threshold_more_hp_decreases(self) -> None:
        """fatigue 95 (default threshold) を超えていれば毎 tick HP-1。

        Y_after_pr634 後続で ``DEFAULT_NEED_RATES[FATIGUE]`` が 0 になったため、
        本テストは passive decay を test 側で明示的に注入し、critical damage
        機構そのもの (= threshold 越え判定 + HP 減少) のみを検証する。"""
        status = _build_status(fatigue_value=94, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(
            repo,
            rates={NeedType.FATIGUE: 1, NeedType.HUNGER: 0},
            fatigue_critical_damage_per_tick=1,
        )

        # 1 tick で FATIGUE 94→95 (threshold 到達) → damage 1
        stage.run(WorldTick(1))

        assert status.needs.get(NeedType.FATIGUE).value == 95
        assert status.hp.value == 99

    def test_fatigue_threshold_below_hp(self) -> None:
        """fatigue 93→94 では threshold 95 に届かないので HP は維持される。"""
        status = _build_status(fatigue_value=93, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(
            repo,
            rates={NeedType.FATIGUE: 1, NeedType.HUNGER: 0},
            fatigue_critical_damage_per_tick=1,
        )

        stage.run(WorldTick(1))

        assert status.needs.get(NeedType.FATIGUE).value == 94
        assert status.hp.value == 100

    def test_custom_threshold(self) -> None:
        """threshold をシナリオで調整できること (例: 90)。"""
        status = _build_status(fatigue_value=89, hp=100)
        repo = MagicMock()
        repo.find_all.return_value = [status]
        stage = SpotGraphNeedsDecayStageService(
            repo,
            rates={NeedType.FATIGUE: 1, NeedType.HUNGER: 0},
            fatigue_critical_damage_per_tick=2,
            fatigue_critical_threshold=90,
        )

        stage.run(WorldTick(1))

        assert status.needs.get(NeedType.FATIGUE).value == 90
        assert status.hp.value == 98
