"""共通シナリオ述語の判定核が用途に依存しない意味を返す仕様。"""

import pytest

from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateReasonCode,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
)
from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PredicateContextValidationException,
)


class TestScenarioPredicateEvaluatorFlagSet:
    """FLAG_SETの完全一致と文脈不足の区別を保証する。"""

    def test_matches_only_exactly_named_flag(self) -> None:
        """同名フラグが集合にあれば成立し、大文字小文字違いでは成立しない。"""
        evaluator = ScenarioPredicateEvaluator()
        context = WorldFlagPredicateContext(frozenset({"door_open"}))

        assert evaluator.evaluate(FlagSetPredicate("door_open"), context).is_satisfied
        assert not evaluator.evaluate(FlagSetPredicate("DOOR_OPEN"), context).is_satisfied

    def test_empty_set_is_normal_unsatisfied(self) -> None:
        """空集合は配線済みの正当な状態なので、文脈不足でなく通常未成立とする。"""
        result = ScenarioPredicateEvaluator().evaluate(
            FlagSetPredicate("ready"),
            WorldFlagPredicateContext(frozenset()),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.missing_context == frozenset()

    def test_missing_flag_set_is_context_missing(self) -> None:
        """世界フラグ集合が未配線なら、通常未成立と区別して必要文脈名を返す。"""
        result = ScenarioPredicateEvaluator().evaluate(
            FlagSetPredicate("ready"),
            WorldFlagPredicateContext(None),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"world_flags"})

    @pytest.mark.parametrize("world_flags", [set(), [], frozenset({""}), frozenset({1})])
    def test_context_rejects_mutable_or_invalid_flag_collections(
        self, world_flags: object,
    ) -> None:
        """可変集合や不正な要素を受け入れず、評価中の意味変化を防ぐ。"""
        with pytest.raises(PredicateContextValidationException):
            WorldFlagPredicateContext(world_flags)  # type: ignore[arg-type]
