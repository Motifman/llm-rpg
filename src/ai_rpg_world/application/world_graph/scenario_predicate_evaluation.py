"""一度のシナリオ述語評価で得た結果と確率判断の診断値。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateResult,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)


@dataclass(frozen=True)
class ProbabilityDecision:
    """PROBABILITY leafが実際に消費した乱数と判定。"""

    path: tuple[int, ...]
    probability: float
    sampled_value: float
    is_satisfied: bool


@dataclass(frozen=True)
class ScenarioPredicateEvaluation:
    """根の評価結果と、短絡されず実行された確率判断。"""

    result: PredicateResult[ScenarioEventCondition]
    probability_decisions: tuple[ProbabilityDecision, ...]


__all__ = ["ProbabilityDecision", "ScenarioPredicateEvaluation"]
