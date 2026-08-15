"""腐敗食の消費数値計算 (spoiled_consumption) の仕様テスト。"""

from __future__ import annotations

from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    HealEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.domain.item.value_object.spoiled_consumption import (
    SPOILED_FOOD_DAMAGE_HP,
    hunger_satisfaction_amount,
    spoiled_consumption_outcome,
)


class TestSpoiledConsumptionOutcome:
    """spoiled_consumption_outcome が腐敗食のダメージと空腹半分を返す。"""

    def test_no_consume_effect_returns_damage_only(self) -> None:
        """consume_effect が無いときは damage 10、retained_hunger 0。"""
        outcome = spoiled_consumption_outcome(None)

        assert outcome.damage_hp == SPOILED_FOOD_DAMAGE_HP
        assert outcome.retained_hunger == 0

    def test_heal_only_returns_damage_only(self) -> None:
        """HealEffect だけのときは HP 回復は無視し damage 10、retained_hunger 0。"""
        outcome = spoiled_consumption_outcome(HealEffect(amount=5))

        assert outcome.damage_hp == SPOILED_FOOD_DAMAGE_HP
        assert outcome.retained_hunger == 0

    def test_hunger_35_retains_half_truncated(self) -> None:
        """HUNGER 35 のとき retained_hunger は int(35*0.5)=17。"""
        outcome = spoiled_consumption_outcome(
            SatisfyNeedEffect(need_type_name="HUNGER", amount=35)
        )

        assert outcome.damage_hp == SPOILED_FOOD_DAMAGE_HP
        assert outcome.retained_hunger == 17

    def test_non_hunger_satisfy_need_is_ignored(self) -> None:
        """HUNGER 以外の SatisfyNeedEffect は retained_hunger 0。"""
        outcome = spoiled_consumption_outcome(
            SatisfyNeedEffect(need_type_name="FATIGUE", amount=20)
        )

        assert outcome.damage_hp == SPOILED_FOOD_DAMAGE_HP
        assert outcome.retained_hunger == 0

    def test_composite_heal_and_hunger_matches_executor_fish(self) -> None:
        """Composite (Heal + HUNGER 35) でも retained_hunger 17 (executor の魚と同じ)。"""
        outcome = spoiled_consumption_outcome(
            CompositeItemEffect(
                (
                    HealEffect(amount=5),
                    SatisfyNeedEffect(need_type_name="HUNGER", amount=35),
                )
            )
        )

        assert outcome.damage_hp == SPOILED_FOOD_DAMAGE_HP
        assert outcome.retained_hunger == 17

    def test_hunger_1_truncates_to_zero(self) -> None:
        """HUNGER 1 のとき int(0.5)==0 で retained_hunger 0。"""
        outcome = spoiled_consumption_outcome(
            SatisfyNeedEffect(need_type_name="HUNGER", amount=1)
        )

        assert outcome.damage_hp == SPOILED_FOOD_DAMAGE_HP
        assert outcome.retained_hunger == 0


class TestHungerSatisfactionAmount:
    """hunger_satisfaction_amount がネスト Composite でも HUNGER を合計する。"""

    def test_nested_composite_sums_hunger(self) -> None:
        """ネストした Composite でも HUNGER の satisfy_need 量を合計する。"""
        effect = CompositeItemEffect(
            (
                HealEffect(amount=3),
                CompositeItemEffect(
                    (
                        SatisfyNeedEffect(need_type_name="HUNGER", amount=10),
                        SatisfyNeedEffect(need_type_name="FATIGUE", amount=5),
                    )
                ),
                SatisfyNeedEffect(need_type_name="HUNGER", amount=25),
            )
        )

        assert hunger_satisfaction_amount(effect) == 35
