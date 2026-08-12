"""用途固有の文面や効果を持たない、共通シナリオ述語の評価核。"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateEvaluationException,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateReasonCode,
    PredicateResult,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
    ScenarioPredicate,
)


class ScenarioPredicateEvaluator:
    """型付き述語を副作用なく評価し、不成立と文脈不足を区別する。"""

    def evaluate(
        self,
        predicate: ScenarioPredicate,
        context: WorldFlagPredicateContext,
    ) -> PredicateResult[ScenarioPredicate]:
        """述語を一度評価し、構造化した結果を返す。"""
        if isinstance(predicate, FlagSetPredicate):
            if context.world_flags is None:
                return PredicateResult.context_missing(
                    failed_predicate=predicate,
                    failed_path=(),
                    required_context={"world_flags"},
                )
            if predicate.flag_name in context.world_flags:
                return PredicateResult.satisfied()
            return PredicateResult.not_satisfied(
                failed_predicate=predicate,
                failed_path=(),
            )
        return PredicateResult.unsupported(
            failed_predicate=predicate,
            failed_path=(),
        )

    @staticmethod
    def require_satisfaction(result: PredicateResult[ScenarioPredicate]) -> bool:
        """正常な成立・不成立だけをboolへ射影し、評価不能は即時停止する。"""
        if result.is_satisfied:
            return True
        if result.reason_code is PredicateReasonCode.NOT_SATISFIED:
            return False
        raise ScenarioPredicateEvaluationException(
            "scenario predicate evaluation could not complete: "
            f"reason={result.reason_code.value if result.reason_code else 'unknown'}, "
            f"missing_context={sorted(result.missing_context)}"
        )


__all__ = ["ScenarioPredicateEvaluator"]
