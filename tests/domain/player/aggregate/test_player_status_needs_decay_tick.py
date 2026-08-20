"""PlayerStatusAggregate.apply_needs_decay_tick のドメイン単体テスト。

リポジトリ無しで、欲求の自然増加と飢餓・疲労限界ダメージの判定を検証する。
"""

from __future__ import annotations

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
from ai_rpg_world.domain.player.value_object.needs_decay_tick import (
    DEFAULT_NEED_RATES,
    NeedsDecayTick,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


def _new_status(
    *,
    is_down: bool = False,
    needs: AgentNeeds | None = None,
    hp: int = 100,
) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        is_down=is_down,
        needs=needs,
    )


def _tick(
    *,
    rates: dict[NeedType, int] | None = None,
    starvation_damage_per_tick: int = 0,
    fatigue_critical_damage_per_tick: int = 0,
    fatigue_critical_threshold: int = 95,
) -> NeedsDecayTick:
    return NeedsDecayTick(
        rates=rates or dict(DEFAULT_NEED_RATES),
        starvation_damage_per_tick=starvation_damage_per_tick,
        fatigue_critical_damage_per_tick=fatigue_critical_damage_per_tick,
        fatigue_critical_threshold=fatigue_critical_threshold,
    )


class TestNeedsDecayTickSkipped:
    """ダウン中・needs 空のときは何も変わらない。"""

    def test_downed_player_unchanged(self) -> None:
        """ダウン中は欲求も HP も変化しない。"""
        status = _new_status(is_down=True)
        status.increase_need(NeedType.HUNGER, 50)
        hunger_before = status.needs.get(NeedType.HUNGER)
        assert hunger_before is not None
        hp_before = status.hp.value

        result = status.apply_needs_decay_tick(
            _tick(starvation_damage_per_tick=1, fatigue_critical_damage_per_tick=1)
        )

        assert result.changed is False
        hunger_after = status.needs.get(NeedType.HUNGER)
        assert hunger_after is not None
        assert hunger_after.value == hunger_before.value
        assert status.hp.value == hp_before

    def test_empty_needs_unchanged(self) -> None:
        """needs が空なら何も変化しない。"""
        status = _new_status(needs=AgentNeeds.empty())
        hp_before = status.hp.value

        result = status.apply_needs_decay_tick(
            _tick(rates={NeedType.HUNGER: 1}, starvation_damage_per_tick=1)
        )

        assert result.changed is False
        assert status.hp.value == hp_before


class TestNeedsDecayTickHungerIncrease:
    """空腹の自然増加と飢餓ダメージ。"""

    def test_hunger_increases_below_max_no_damage(self) -> None:
        """max 未満なら HUNGER +1 のみで HP は減らない。"""
        status = _new_status()
        result = status.apply_needs_decay_tick(
            _tick(rates={NeedType.HUNGER: 1}, starvation_damage_per_tick=1)
        )

        assert result.changed is True
        hunger = status.needs.get(NeedType.HUNGER)
        assert hunger is not None
        assert hunger.value == 1
        assert status.hp.value == 100

    def test_starvation_damage_when_reaching_max_this_tick(self) -> None:
        """今 tick で max に達した場合も即座に飢餓ダメージが走る。"""
        status = _new_status()
        status.increase_need(NeedType.HUNGER, 99)

        result = status.apply_needs_decay_tick(
            _tick(rates={NeedType.HUNGER: 1}, starvation_damage_per_tick=2)
        )

        assert result.changed is True
        hunger = status.needs.get(NeedType.HUNGER)
        assert hunger is not None
        assert hunger.value == 100
        assert status.hp.value == 98

    def test_starvation_damage_disabled_when_zero(self) -> None:
        """starvation_damage_per_tick=0 なら hunger max でも HP は減らない。"""
        status = _new_status()
        status.increase_need(NeedType.HUNGER, 100)

        result = status.apply_needs_decay_tick(
            _tick(rates={NeedType.HUNGER: 1}, starvation_damage_per_tick=0)
        )

        assert result.changed is False
        assert status.hp.value == 100


class TestNeedsDecayTickFatigueCritical:
    """疲労限界ダメージ。"""

    def test_fatigue_critical_damage_at_threshold(self) -> None:
        """FATIGUE >= 95 かつ damage > 0 なら HP が減る。"""
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 95)

        result = status.apply_needs_decay_tick(
            _tick(
                rates={NeedType.FATIGUE: 0},
                fatigue_critical_damage_per_tick=3,
            )
        )

        assert result.changed is True
        assert status.hp.value == 97

    def test_fatigue_below_threshold_no_damage(self) -> None:
        """threshold 未満なら HP は減らない。"""
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 94)

        result = status.apply_needs_decay_tick(
            _tick(
                rates={NeedType.FATIGUE: 0},
                fatigue_critical_damage_per_tick=3,
            )
        )

        assert result.changed is False
        assert status.hp.value == 100

    def test_custom_fatigue_threshold(self) -> None:
        """カスタム threshold (例: 90) が効く。"""
        status = _new_status()
        status.increase_need(NeedType.FATIGUE, 90)

        result = status.apply_needs_decay_tick(
            _tick(
                rates={NeedType.FATIGUE: 0},
                fatigue_critical_damage_per_tick=1,
                fatigue_critical_threshold=90,
            )
        )

        assert result.changed is True
        assert status.hp.value == 99


class TestNeedsDecayTickCombined:
    """複合ケース。"""

    def test_starvation_and_fatigue_critical_both_apply(self) -> None:
        """飢餓と疲労限界ダメージは独立に同 tick で両方かかり得る。"""
        status = _new_status()
        status.increase_need(NeedType.HUNGER, 100)
        status.increase_need(NeedType.FATIGUE, 95)

        result = status.apply_needs_decay_tick(
            _tick(
                rates={NeedType.HUNGER: 0, NeedType.FATIGUE: 0},
                starvation_damage_per_tick=2,
                fatigue_critical_damage_per_tick=3,
            )
        )

        assert result.changed is True
        assert status.hp.value == 95

    def test_zero_rate_need_does_not_increase(self) -> None:
        """rate <= 0 の need は増えない。"""
        status = _new_status()
        fatigue_before = status.needs.get(NeedType.FATIGUE)
        assert fatigue_before is not None
        assert fatigue_before.value == 0

        result = status.apply_needs_decay_tick(
            _tick(rates={NeedType.HUNGER: 1, NeedType.FATIGUE: 0})
        )

        assert result.changed is True
        fatigue_after = status.needs.get(NeedType.FATIGUE)
        assert fatigue_after is not None
        assert fatigue_after.value == 0
        hunger = status.needs.get(NeedType.HUNGER)
        assert hunger is not None
        assert hunger.value == 1
