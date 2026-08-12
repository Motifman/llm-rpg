"""ScenarioConditionEvaluator が理由・経路・短絡順を保つ契約。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateReasonCode,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


class _CountingRandom:
    """指定値を順に返し、短絡による呼出し回数を観測できる乱数源。"""

    def __init__(self, *values: float) -> None:
        self._values = iter(values)
        self.call_count = 0

    def random(self) -> float:
        self.call_count += 1
        return next(self._values)


def _condition(condition_type: str, **kwargs: object) -> ScenarioEventCondition:
    return ScenarioEventCondition(condition_type=condition_type, **kwargs)


def _graph() -> SpotGraphAggregate:
    return SpotGraphAggregate.empty(SpotGraphId.create(1))


def _evaluator(
    *,
    random_source: object | None = None,
    weather_provider: object | None = None,
    inventory_missing: bool = False,
    game_phase_provider: object | None = None,
) -> ScenarioConditionEvaluator:
    status_repository = MagicMock()
    status_repository.find_all.return_value = ()
    inventory_repository = MagicMock()
    if inventory_missing:
        inventory_repository.find_by_id.return_value = None
    return ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=MagicMock(),
        player_status_repository=status_repository,
        player_inventory_repository=inventory_repository,
        item_repository=MagicMock(),
        weather_state_provider=weather_provider,
        game_phase_provider=game_phase_provider,
        random_source=random_source,  # type: ignore[arg-type]
    )


class TestLeafPredicateResults:
    """leaf条件が通常未成立・文脈不足・未対応を区別して返す。"""

    def test_world_state_mismatch_is_normal_unsatisfied(self) -> None:
        """未設定フラグとの不一致は、入力不足ではなく通常未成立とする。"""
        condition = _condition("FLAG_SET", flag_name="not_set")

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.is_satisfied is False
        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        assert result.missing_context == frozenset()

    def test_missing_weather_provider_names_required_context(self) -> None:
        """天候provider未配線は通常の天候不一致へ潰さず、入力名を返す。"""
        condition = _condition("WEATHER_IS", weather_type="RAIN")

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        assert result.missing_context == frozenset({"weather_state"})

    def test_unknown_condition_is_unsupported(self) -> None:
        """直接構築された未知条件は通常未成立でなく評価器未対応とする。"""
        condition = _condition("UNKNOWN")

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.UNSUPPORTED_PREDICATE
        assert result.failed_predicate is condition
        assert result.failed_path == ()

    def test_unplaced_target_player_is_normal_unsatisfied(self) -> None:
        """退場済みの対象者が場所にいない状態は文脈不足にしない。"""
        condition = _condition("PLAYER_AT_SPOT", spot_id=1)

        result = _evaluator().evaluate_result_for_player(
            condition,
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(1),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED

    def test_missing_object_is_context_missing(self) -> None:
        """宣言済みobjectを世界から解決できない場合は入力不足として返す。"""
        condition = _condition(
            "OBJECT_STATE",
            object_id=1,
            required_state={"open": True},
        )

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"spot_object"})

    def test_missing_player_inventory_is_context_missing(self) -> None:
        """対象者のinventory不在はアイテム未所持と区別する。"""
        condition = _condition("HAS_ITEM", item_spec_id=1)

        result = _evaluator(inventory_missing=True).evaluate_result_for_player(
            condition,
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(1),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"player_inventory"})

    def test_game_phase_result_is_missing_but_bool_api_still_raises(self) -> None:
        """phase未配線を結果では分類し、既存bool入口では従来どおり停止する。"""
        condition = _condition("GAME_PHASE_IS", game_phase="MEETING")
        evaluator = _evaluator()

        result = evaluator.evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"game_phase"})
        with pytest.raises(RuntimeError, match="game_phase_provider"):
            evaluator.evaluate(condition, WorldTick(0), _graph())

    def test_bool_api_rejects_nested_game_phase_before_evaluation(self) -> None:
        """合成条件内のphase未配線も、既存bool入口では評価前に停止する。"""
        condition = _condition(
            "OR",
            children=(
                _condition("GAME_PHASE_IS", game_phase="MEETING"),
                _condition("TICK_AT_LEAST", tick=0),
            ),
        )

        with pytest.raises(RuntimeError, match="game_phase_provider"):
            _evaluator().evaluate(condition, WorldTick(0), _graph())

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())
        assert result.is_satisfied is True


class TestCompositePredicateResults:
    """合成条件が文脈不足を反転せず、原因までの経路を保持する。"""

    def test_not_does_not_turn_missing_context_into_true(self) -> None:
        """NOT配下で天候providerが無くても、条件成立へ反転しない。"""
        weather = _condition("WEATHER_IS", weather_type="RAIN")
        condition = _condition("NOT", children=(weather,))

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.is_satisfied is False
        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_predicate is weather
        assert result.failed_path == (0,)

    def test_not_propagates_unsupported_child(self) -> None:
        """NOT配下の未知条件も真へ反転せず、未対応のまま返す。"""
        unknown = _condition("UNKNOWN")
        condition = _condition("NOT", children=(unknown,))

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.UNSUPPORTED_PREDICATE
        assert result.failed_path == (0,)

    def test_and_stops_at_missing_before_probability(self) -> None:
        """ANDは文脈不足をFalse同様に短絡し、後続乱数を消費しない。"""
        random_source = _CountingRandom(0.0)
        condition = _condition(
            "AND",
            children=(
                _condition("WEATHER_IS", weather_type="RAIN"),
                _condition("PROBABILITY", probability=1.0),
            ),
        )

        result = _evaluator(random_source=random_source).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_path == (0,)
        assert random_source.call_count == 0

    def test_or_allows_later_true_to_win_over_missing(self) -> None:
        """ORは最初の文脈不足を記憶しつつ、後続成立があれば成立する。"""
        random_source = _CountingRandom(0.0)
        condition = _condition(
            "OR",
            children=(
                _condition("WEATHER_IS", weather_type="RAIN"),
                _condition("PROBABILITY", probability=1.0),
            ),
        )

        result = _evaluator(random_source=random_source).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.is_satisfied is True
        assert random_source.call_count == 1

    def test_or_returns_first_missing_when_no_child_matches(self) -> None:
        """ORが全て不成立なら、最初の文脈不足と入れ子経路を返す。"""
        condition = _condition(
            "AND",
            children=(
                _condition("TICK_AT_LEAST", tick=0),
                _condition(
                    "OR",
                    children=(
                        _condition("FLAG_SET", flag_name="not_set"),
                        _condition("WEATHER_IS", weather_type="RAIN"),
                    ),
                ),
            ),
        )

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_path == (1, 1)

    def test_or_with_only_normal_failures_points_to_composite_root(self) -> None:
        """ORの全子が通常未成立なら、単独原因を偽らずOR自身を指す。"""
        condition = _condition(
            "OR",
            children=(
                _condition("FLAG_SET", flag_name="a"),
                _condition("FLAG_SET", flag_name="b"),
            ),
        )

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()

    def test_not_of_true_points_to_not_root(self) -> None:
        """成立した子を反転したNOTの未成立原因は、子ではなくNOT自身とする。"""
        condition = _condition(
            "NOT",
            children=(_condition("TICK_AT_LEAST", tick=0),),
        )

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()

    def test_empty_or_is_normal_unsatisfied_at_root(self) -> None:
        """子のないORは従来どおり不成立で、OR自身を原因として返す。"""
        condition = _condition("OR", children=())

        result = _evaluator().evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()


class TestImplicitAndAndCompatibility:
    """複数条件入口の経路と、既存真偽値入口への射影を保証する。"""

    def test_implicit_and_prefixes_failed_condition_index(self) -> None:
        """暗黙ANDの2番目で落ちると、根からの経路は子番号1になる。"""
        failed = _condition("FLAG_SET", flag_name="not_set")

        result = _evaluator().evaluate_all_result(
            (_condition("TICK_AT_LEAST", tick=0), failed),
            WorldTick(0),
            _graph(),
        )

        assert result.failed_predicate is failed
        assert result.failed_path == (1,)

    def test_boolean_entry_is_exact_projection_of_result(self) -> None:
        """既存evaluateは同じ条件の構造化結果から成否だけを返す。"""
        condition = _condition("FLAG_SET", flag_name="not_set")
        evaluator = _evaluator()

        result = evaluator.evaluate_result(condition, WorldTick(0), _graph())
        legacy = evaluator.evaluate(condition, WorldTick(0), _graph())

        assert legacy is result.is_satisfied

    def test_probability_zero_and_one_each_consume_one_draw(self) -> None:
        """確率0と1も定数最適化せず、評価ごとに乱数を1回消費する。"""
        random_source = _CountingRandom(0.5, 0.5)
        evaluator = _evaluator(random_source=random_source)

        zero = evaluator.evaluate_result(
            _condition("PROBABILITY", probability=0.0),
            WorldTick(0),
            _graph(),
        )
        one = evaluator.evaluate_result(
            _condition("PROBABILITY", probability=1.0),
            WorldTick(0),
            _graph(),
        )

        assert zero.is_satisfied is False
        assert one.is_satisfied is True
        assert random_source.call_count == 2

    def test_and_normal_failure_skips_later_probability(self) -> None:
        """ANDの通常未成立でも後続確率条件の乱数を消費しない。"""
        random_source = _CountingRandom(0.0)
        condition = _condition(
            "AND",
            children=(
                _condition("FLAG_SET", flag_name="not_set"),
                _condition("PROBABILITY", probability=1.0),
            ),
        )

        result = _evaluator(random_source=random_source).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.is_satisfied is False
        assert random_source.call_count == 0

    def test_or_true_skips_later_probability(self) -> None:
        """ORの先頭成立では後続確率条件の乱数を消費しない。"""
        random_source = _CountingRandom(0.0)
        condition = _condition(
            "OR",
            children=(
                _condition("TICK_AT_LEAST", tick=0),
                _condition("PROBABILITY", probability=1.0),
            ),
        )

        result = _evaluator(random_source=random_source).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.is_satisfied is True
        assert random_source.call_count == 0

    def test_implicit_and_missing_skips_later_probability(self) -> None:
        """暗黙ANDも文脈不足で停止し、後続乱数を消費しない。"""
        random_source = _CountingRandom(0.0)

        result = _evaluator(random_source=random_source).evaluate_all_result(
            (
                _condition("WEATHER_IS", weather_type="RAIN"),
                _condition("PROBABILITY", probability=1.0),
            ),
            WorldTick(0),
            _graph(),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert random_source.call_count == 0

    def test_empty_implicit_and_remains_true(self) -> None:
        """条件なしの暗黙ANDは従来どおり成立する。"""
        result = _evaluator().evaluate_all_result((), WorldTick(0), _graph())

        assert result.is_satisfied is True
