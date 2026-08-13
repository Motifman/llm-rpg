"""共通述語を実際に利用する用途の監査用対応表。"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping

from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    EntityAtSpotPredicate,
    EntityCountAtSpotAtLeastPredicate,
    FlagSetPredicate,
    ItemSpecCountAtLeastPredicate,
    ItemSpecOwnedPredicate,
    StateIntAtLeastPredicate,
    StateValuesMatchPredicate,
    TickAtLeastPredicate,
    WeatherTypeIsPredicate,
)


class ScenarioPredicateUsage(str, Enum):
    """旧DTOから共通述語へ変換している利用用途。"""

    SCENARIO_CONDITION = "scenario_condition"
    GAME_END = "game_end"
    INTERACTION = "interaction"
    PASSAGE = "passage"
    DISCOVERY = "discovery"
    MONSTER_SPAWN = "monster_spawn"


PREDICATE_ALLOWED_USAGES: Mapping[
    type[object], frozenset[ScenarioPredicateUsage]
] = MappingProxyType({
    FlagSetPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.GAME_END,
        ScenarioPredicateUsage.INTERACTION,
        ScenarioPredicateUsage.PASSAGE,
        ScenarioPredicateUsage.DISCOVERY,
        ScenarioPredicateUsage.MONSTER_SPAWN,
    }),
    TickAtLeastPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.GAME_END,
    }),
    EntityAtSpotPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.GAME_END,
    }),
    EntityCountAtSpotAtLeastPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
    }),
    ItemSpecOwnedPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.INTERACTION,
        ScenarioPredicateUsage.PASSAGE,
        ScenarioPredicateUsage.DISCOVERY,
    }),
    ItemSpecCountAtLeastPredicate: frozenset({
        ScenarioPredicateUsage.INTERACTION,
    }),
    StateValuesMatchPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.INTERACTION,
    }),
    StateIntAtLeastPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.INTERACTION,
    }),
    WeatherTypeIsPredicate: frozenset({
        ScenarioPredicateUsage.SCENARIO_CONDITION,
        ScenarioPredicateUsage.INTERACTION,
        ScenarioPredicateUsage.MONSTER_SPAWN,
    }),
})


__all__ = ["PREDICATE_ALLOWED_USAGES", "ScenarioPredicateUsage"]
