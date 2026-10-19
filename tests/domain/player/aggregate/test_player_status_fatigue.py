"""PR β: PlayerStatusAggregate の疲労ライフサイクル API。

- apply_fatigue / recover_fatigue が需要値を increase/satisfy する
- fatigue_value / fatigue_level が tier 文字列を正しく返す
- is_fatigued / is_severely_fatigued / is_exhausted の閾値判定
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.agent_needs import AgentNeeds
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


def _new_status(*, needs: AgentNeeds | None = None) -> PlayerStatusAggregate:
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
        needs=needs,
    )


class TestFatigueApplyRecover:
    """疲労の上げ下げと境界値の振る舞い。"""

    @pytest.mark.parametrize("needs", [None, AgentNeeds.empty()], ids=["default", "empty"])
    def test_default_or_unregistered_fatigue_value_zero(self, needs: AgentNeeds | None) -> None:
        """既定の疲労0とFATIGUE未登録のどちらも、値0・段階okを返す。"""
        status = _new_status(needs=needs)
        if needs is not None:
            assert status.needs.get(NeedType.FATIGUE) is None
        assert status.fatigue_value == 0
        assert status.fatigue_level == "ok"

    def test_apply_fatigue_value_increases(self) -> None:
        """apply fatigue で値が増加する。"""
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 0)  # 既定の疲労0を維持する
        status.apply_fatigue(40)
        assert status.fatigue_value == 40

    def test_recover_fatigue_value_decreases(self) -> None:
        """recover fatigue で値が減少する。"""
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 70)
        status.recover_fatigue(30)
        assert status.fatigue_value == 40


class TestFatigueLevelTiers:
    """疲労の各段階と公開判定を、閾値の直前と到達時で保証する。"""

    @pytest.mark.parametrize(
        "value, level, fatigued, severe, exhausted",
        [
            (0, "ok", False, False, False),
            (29, "ok", False, False, False),
            (30, "tired", False, False, False),
            (59, "tired", False, False, False),
            (60, "fatigued", True, False, False),
            (84, "fatigued", True, False, False),
            (85, "severe", True, True, False),
            (99, "severe", True, True, False),
            (100, "exhausted", True, True, True),
        ],
    )
    def test_fatigue_tiers_and_threshold_predicates(
        self,
        value: int,
        level: str,
        fatigued: bool,
        severe: bool,
        exhausted: bool,
    ) -> None:
        """0/30/60/85/100で段階が切り替わり、各判定は自身の閾値以上で真になる。"""
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, value)

        assert status.fatigue_level == level
        assert status.is_fatigued() is fatigued
        assert status.is_severely_fatigued() is severe
        assert status.is_exhausted() is exhausted
