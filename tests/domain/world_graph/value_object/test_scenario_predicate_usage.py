"""共通述語の型・評価分岐・利用用途が同時に追従する構造を保証する。"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import get_args

from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    PREDICATE_CONTEXT_TYPES,
    PredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    SCENARIO_PREDICATE_TYPES,
    EntityAtSpotPredicate,
    EntityCountAtSpotAtLeastPredicate,
    FlagSetPredicate,
    ItemSpecCountAtLeastPredicate,
    ItemSpecOwnedPredicate,
    ScenarioPredicate,
    StateIntAtLeastPredicate,
    StateValuesMatchPredicate,
    TickAtLeastPredicate,
    WeatherTypeIsPredicate,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate_usage import (
    PREDICATE_ALLOWED_USAGES,
    ScenarioPredicateUsage,
)


def _evaluated_predicate_type_names() -> set[str]:
    """評価器の `isinstance(predicate, Type)` 分岐から型名を抽出する。"""
    tree = ast.parse(textwrap.dedent(
        inspect.getsource(ScenarioPredicateEvaluator.evaluate)
    ))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "isinstance":
            continue
        if len(node.args) != 2:
            continue
        subject, expected_type = node.args
        if (
            isinstance(subject, ast.Name)
            and subject.id == "predicate"
            and isinstance(expected_type, ast.Name)
        ):
            names.add(expected_type.id)
    return names


class TestScenarioPredicateStructuralCoverage:
    """新しい述語型が評価器や用途表から静かに漏れないことを保証する。"""

    def test_type_alias_and_runtime_types_match(self) -> None:
        """型aliasへ追加した述語は実行時型一覧にも過不足なく現れる。"""
        assert set(get_args(ScenarioPredicate)) == set(SCENARIO_PREDICATE_TYPES)

    def test_every_predicate_has_an_evaluator_branch(self) -> None:
        """全共通述語に評価分岐があり、廃止型の分岐も残っていない。"""
        assert _evaluated_predicate_type_names() == {
            predicate_type.__name__ for predicate_type in SCENARIO_PREDICATE_TYPES
        }

    def test_context_alias_and_runtime_types_match(self) -> None:
        """評価文脈の型aliasと実行時型一覧を双方向に一致させる。"""
        assert set(get_args(PredicateContext)) == set(PREDICATE_CONTEXT_TYPES)

    def test_every_predicate_is_classified_by_usage(self) -> None:
        """全共通述語を少なくとも一つの実利用用途へ分類する。"""
        assert set(PREDICATE_ALLOWED_USAGES) == set(SCENARIO_PREDICATE_TYPES)
        assert all(PREDICATE_ALLOWED_USAGES.values())
        assert all(
            isinstance(usage, ScenarioPredicateUsage)
            for usages in PREDICATE_ALLOWED_USAGES.values()
            for usage in usages
        )

    def test_usage_matrix_records_only_migrated_meanings(self) -> None:
        """名前が似るだけの用途へ共通述語を誤って許可しない。"""
        s = ScenarioPredicateUsage
        assert PREDICATE_ALLOWED_USAGES == {
            FlagSetPredicate: frozenset({
                s.SCENARIO_CONDITION, s.GAME_END, s.INTERACTION,
                s.PASSAGE, s.DISCOVERY, s.MONSTER_SPAWN,
            }),
            TickAtLeastPredicate: frozenset({s.SCENARIO_CONDITION, s.GAME_END}),
            EntityAtSpotPredicate: frozenset({s.SCENARIO_CONDITION, s.GAME_END}),
            EntityCountAtSpotAtLeastPredicate: frozenset({s.SCENARIO_CONDITION}),
            ItemSpecOwnedPredicate: frozenset({
                s.SCENARIO_CONDITION, s.INTERACTION, s.PASSAGE, s.DISCOVERY,
            }),
            ItemSpecCountAtLeastPredicate: frozenset({s.INTERACTION}),
            StateValuesMatchPredicate: frozenset({
                s.SCENARIO_CONDITION, s.INTERACTION,
            }),
            StateIntAtLeastPredicate: frozenset({
                s.SCENARIO_CONDITION, s.INTERACTION,
            }),
            WeatherTypeIsPredicate: frozenset({
                s.SCENARIO_CONDITION, s.INTERACTION, s.MONSTER_SPAWN,
            }),
        }
