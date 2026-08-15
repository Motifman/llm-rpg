from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ItemEffect,
    SatisfyNeedEffect,
)

SPOILED_FOOD_DAMAGE_HP = 10
SPOILED_FOOD_HUNGER_RETENTION_RATIO = 0.5
HUNGER_NEED_TYPE_NAME = "HUNGER"


@dataclass(frozen=True)
class SpoiledConsumptionOutcome:
    """腐敗食を食べたときに発生する数値。適用は application が行う。"""

    damage_hp: int
    retained_hunger: int


def hunger_satisfaction_amount(effect: ItemEffect | None) -> int:
    """consume_effect から HUNGER の satisfy_need 量だけを合計する。"""
    if effect is None:
        return 0
    if isinstance(effect, SatisfyNeedEffect):
        if effect.need_type_name != HUNGER_NEED_TYPE_NAME:
            return 0
        return effect.amount
    if isinstance(effect, CompositeItemEffect):
        return sum(hunger_satisfaction_amount(sub) for sub in effect.effects)
    return 0


def spoiled_consumption_outcome(
    consume_effect: ItemEffect | None,
) -> SpoiledConsumptionOutcome:
    hunger = hunger_satisfaction_amount(consume_effect)
    retained = int(hunger * SPOILED_FOOD_HUNGER_RETENTION_RATIO)
    return SpoiledConsumptionOutcome(
        damage_hp=SPOILED_FOOD_DAMAGE_HP,
        retained_hunger=retained,
    )
