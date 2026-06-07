"""PR β: PlayerStatusAggregate の疲労ライフサイクル API。

- apply_fatigue / recover_fatigue が需要値を increase/satisfy する
- fatigue_value / fatigue_level が tier 文字列を正しく返す
- is_fatigued / is_severely_fatigued / is_exhausted の閾値判定
"""

from __future__ import annotations

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


def _new_status() -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


class TestFatigueApplyRecover:
    """疲労の上げ下げと境界値の振る舞い。"""

    def test_FATIGUE_未登録時は_fatigue_value_は_0(self) -> None:
        status = _new_status()
        assert status.fatigue_value == 0
        assert status.fatigue_level == "ok"

    def test_apply_fatigue_で値が増加する(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 0)  # FATIGUE need を初期化
        status.apply_fatigue(40)
        assert status.fatigue_value == 40

    def test_recover_fatigue_で値が減少する(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 70)
        status.recover_fatigue(30)
        assert status.fatigue_value == 40


class TestFatigueLevelTiers:
    """fatigue_value → tier 文字列のマッピング。"""

    def test_0_から_29_は_ok(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 29)
        assert status.fatigue_level == "ok"

    def test_30_から_59_は_tired(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 30)
        assert status.fatigue_level == "tired"

    def test_60_から_84_は_fatigued(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 60)
        assert status.fatigue_level == "fatigued"
        assert status.is_fatigued() is True

    def test_85_から_99_は_severe(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 85)
        assert status.fatigue_level == "severe"
        assert status.is_severely_fatigued() is True

    def test_100_は_exhausted(self) -> None:
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 100)
        assert status.fatigue_level == "exhausted"
        assert status.is_exhausted() is True
