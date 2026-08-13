"""ScenarioConditionEvaluator が理由・経路・短絡順を保つ契約。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateResult,
    PredicateReasonCode,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    StateIntAtLeastPredicate,
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
    predicate_evaluator: object | None = None,
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
        predicate_evaluator=predicate_evaluator,  # type: ignore[arg-type]
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

    def test_flag_set_delegates_to_typed_common_evaluator(self) -> None:
        """FLAG_SETは旧DTOを保ったまま、真偽判定を共通の型付き評価核へ委譲する。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.satisfied()
        condition = _condition("FLAG_SET", flag_name="not_set")

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.is_satisfied is True
        predicate, context = common.evaluate.call_args.args
        assert predicate.flag_name == "not_set"
        assert context.world_flags == frozenset()

    def test_flag_set_preserves_common_unsupported_result(self) -> None:
        """共通評価核の未対応は通常不成立へ潰さず、元DTOへ写して返す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.unsupported(
            failed_predicate=MagicMock(),
            failed_path=(),
        )
        condition = _condition("FLAG_SET", flag_name="not_set")

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.reason_code is PredicateReasonCode.UNSUPPORTED_PREDICATE
        assert result.failed_predicate is condition
        assert result.failed_path == ()

    def test_tick_at_least_delegates_and_restores_legacy_predicate(self) -> None:
        """TICK_AT_LEASTは共通核へ委譲し、不成立時は元の旧DTOを返す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=MagicMock(),
            failed_path=(),
        )
        condition = _condition("TICK_AT_LEAST", tick=10)

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(9), _graph(),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        predicate, context = common.evaluate.call_args.args
        assert predicate.threshold == 10
        assert context.current_tick == WorldTick(9)

    def test_tick_at_least_missing_definition_keeps_legacy_unsatisfied(self) -> None:
        """tick欠落の旧DTOは共通核を呼ばず、従来どおり通常未成立とする。"""
        common = MagicMock()
        condition = _condition("TICK_AT_LEAST")

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        common.evaluate.assert_not_called()

    def test_tick_at_least_keeps_legacy_string_coercion_at_adapter(self) -> None:
        """文字列tickの旧変換は互換入口に残し、共通核には整数を渡す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.satisfied()
        condition = _condition("TICK_AT_LEAST", tick="10")

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(10), _graph(),
        )

        assert result.is_satisfied is True
        predicate, _ = common.evaluate.call_args.args
        assert predicate.threshold == 10

    def test_nested_tick_at_least_failure_keeps_path_and_condition_type(self) -> None:
        """共通化後もネストしたtick条件の失敗経路と旧条件種別を維持する。"""
        tick_condition = _condition("TICK_AT_LEAST", tick=10)
        condition = _condition(
            "AND",
            children=(
                _condition("FLAG_NOT_SET", flag_name="never_set"),
                tick_condition,
            ),
        )

        result = _evaluator().evaluate_result(condition, WorldTick(9), _graph())

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is tick_condition
        assert result.failed_predicate.condition_type == "TICK_AT_LEAST"
        assert result.failed_path == (1,)

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

    @pytest.mark.parametrize("condition_type", ["PLAYER_AT_SPOT", "PLAYERS_AT_SPOT"])
    def test_location_condition_restores_legacy_predicate_on_common_failure(
        self, condition_type: str,
    ) -> None:
        """場所共通核の入力不足は通常falseへ潰さず、元の条件型と経路へ写す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.context_missing(
            failed_predicate=MagicMock(),
            failed_path=(),
            required_context={"entity_locations"},
        )
        condition = _condition(
            condition_type,
            spot_id=1,
            required_player_count=2 if condition_type == "PLAYERS_AT_SPOT" else None,
        )

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        assert result.missing_context == frozenset({"entity_locations"})

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

    def test_object_state_delegates_and_restores_legacy_predicate(self) -> None:
        """OBJECT_STATEはstate一致を共通核へ委譲し、不成立を元DTOへ写す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=MagicMock(), failed_path=(),
        )
        condition = _condition(
            "OBJECT_STATE", object_id=1, required_state={"open": True},
        )
        obj = MagicMock(state={"open": False, "extra": 1})

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=obj,
        ):
            result = _evaluator(predicate_evaluator=common).evaluate_result(
                condition, WorldTick(0), _graph(),
            )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        predicate, context = common.evaluate.call_args.args
        assert dict(predicate.required_values) == {"open": True}
        assert dict(context.state_values) == {"open": False, "extra": 1}

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_object_state_preserves_common_indeterminate_result(
        self, reason: str,
    ) -> None:
        """state共通核の入力不足・未対応を元OBJECT_STATEへ写して保持する。"""
        common = MagicMock()
        failed = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"state_values"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(
                failed_predicate=failed, failed_path=(),
            )
        )
        condition = _condition(
            "OBJECT_STATE", object_id=1, required_state={"open": True},
        )

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=MagicMock(state={"open": False}),
        ):
            result = _evaluator(predicate_evaluator=common).evaluate_result(
                condition, WorldTick(0), _graph(),
            )

        assert result.reason_code is (
            PredicateReasonCode.MISSING_CONTEXT
            if reason == "missing"
            else PredicateReasonCode.UNSUPPORTED_PREDICATE
        )
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        assert result.missing_context == (
            frozenset({"state_values"}) if reason == "missing" else frozenset()
        )

    def test_object_state_int_at_least_delegates_and_restores_legacy_predicate(
        self,
    ) -> None:
        """整数state下限を共通核へ一度委譲し、不成立を元DTOへ写す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=MagicMock(), failed_path=(),
        )
        condition = _condition(
            "OBJECT_STATE_INT_AT_LEAST",
            object_id=1,
            state_key="count",
            ticks_offset="3",
        )
        obj = MagicMock(state={"count": 2})

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=obj,
        ):
            result = _evaluator(predicate_evaluator=common).evaluate_result(
                condition, WorldTick(0), _graph(),
            )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        common.evaluate.assert_called_once()
        predicate, context = common.evaluate.call_args.args
        assert predicate == StateIntAtLeastPredicate("count", 3)
        assert dict(context.state_values) == {"count": 2}

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_object_state_int_at_least_preserves_common_indeterminate_result(
        self, reason: str,
    ) -> None:
        """整数state共通核の入力不足・未対応を元条件へ写して保持する。"""
        common = MagicMock()
        failed = StateIntAtLeastPredicate("count", 3)
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"state_values"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(
                failed_predicate=failed, failed_path=(),
            )
        )
        condition = _condition(
            "OBJECT_STATE_INT_AT_LEAST",
            object_id=1,
            state_key="count",
            ticks_offset=3,
        )

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=MagicMock(state={"count": 2}),
        ):
            result = _evaluator(predicate_evaluator=common).evaluate_result(
                condition, WorldTick(0), _graph(),
            )

        assert result.reason_code is (
            PredicateReasonCode.MISSING_CONTEXT
            if reason == "missing"
            else PredicateReasonCode.UNSUPPORTED_PREDICATE
        )
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        assert result.missing_context == (
            frozenset({"state_values"}) if reason == "missing" else frozenset()
        )

    def test_invalid_object_state_int_definition_skips_common_evaluator(self) -> None:
        """必須field欠落の旧DTOは共通核へ渡さず従来どおり通常不成立にする。"""
        common = MagicMock()
        condition = _condition(
            "OBJECT_STATE_INT_AT_LEAST", object_id=1, state_key="count",
        )

        result = _evaluator(predicate_evaluator=common).evaluate_result(
            condition, WorldTick(0), _graph(),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        common.evaluate.assert_not_called()

    def test_missing_object_state_int_target_is_context_missing(self) -> None:
        """宣言した対象objectを解決できなければ整数0でなくspot_object不足を返す。"""
        condition = _condition(
            "OBJECT_STATE_INT_AT_LEAST",
            object_id=1,
            state_key="count",
            ticks_offset=1,
        )

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=None,
        ):
            result = _evaluator().evaluate_result(
                condition, WorldTick(0), _graph(),
            )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_predicate is condition
        assert result.missing_context == frozenset({"spot_object"})

    def test_nested_object_state_int_failure_keeps_path_and_skips_probability(
        self,
    ) -> None:
        """整数state不足は子経路を保持し、後続の確率条件を評価しない。"""
        random_source = _CountingRandom(0.0)
        state_condition = _condition(
            "OBJECT_STATE_INT_AT_LEAST",
            object_id=1,
            state_key="count",
            ticks_offset=3,
        )
        condition = _condition(
            "AND",
            children=(
                state_condition,
                _condition("PROBABILITY", probability=1.0),
            ),
        )

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=MagicMock(state={"count": 2}),
        ):
            result = _evaluator(random_source=random_source).evaluate_result(
                condition, WorldTick(0), _graph(),
            )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is state_condition
        assert result.failed_path == (0,)
        assert random_source.call_count == 0

    def test_matching_object_state_int_evaluates_following_probability_once(
        self,
    ) -> None:
        """整数state成立後だけ後続確率を一度評価し、乱数消費順を維持する。"""
        random_source = _CountingRandom(0.0)
        condition = _condition(
            "AND",
            children=(
                _condition(
                    "OBJECT_STATE_INT_AT_LEAST",
                    object_id=1,
                    state_key="count",
                    ticks_offset=3,
                ),
                _condition("PROBABILITY", probability=1.0),
            ),
        )

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator.find_object_in_graph",
            return_value=MagicMock(state={"count": 3}),
        ):
            evaluation = _evaluator(
                random_source=random_source,
            ).evaluate_diagnostic(condition, WorldTick(0), _graph())

        assert evaluation.result.is_satisfied
        assert random_source.call_count == 1
        assert len(evaluation.probability_decisions) == 1
        assert evaluation.probability_decisions[0].path == (1,)

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

    def test_has_item_restores_legacy_predicate_after_common_evaluation(self) -> None:
        """品目共通核の不成立を元のHAS_ITEM条件と失敗経路へ写し戻す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=MagicMock(),
            failed_path=(),
        )
        condition = _condition("HAS_ITEM", item_spec_id=1)
        evaluator = _evaluator(predicate_evaluator=common)
        inventory = MagicMock(max_slots=0)
        inventory.get_item_instance_id_by_equipment_slot.return_value = None
        evaluator._player_inventory_repository.find_by_id.return_value = inventory

        result = evaluator.evaluate_result_for_player(
            condition,
            WorldTick(0),
            _graph(),
            target_player_id=PlayerId(1),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.failed_predicate is condition
        assert result.failed_path == ()
        predicate, context = common.evaluate.call_args.args
        assert predicate.item_spec_id.value == 1
        assert context.owned_item_spec_ids == frozenset()

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_player_has_item_preserves_common_indeterminate_result(
        self, reason: str,
    ) -> None:
        """対象者の所持評価不能を通常未所持へ潰さず、元の条件へ写し戻す。"""
        common = MagicMock()
        failed = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"owned_item_spec_ids"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(failed_predicate=failed, failed_path=())
        )
        condition = _condition("HAS_ITEM", item_spec_id=1)
        evaluator = _evaluator(predicate_evaluator=common)
        inventory = MagicMock(max_slots=0)
        inventory.get_item_instance_id_by_equipment_slot.return_value = None
        evaluator._player_inventory_repository.find_by_id.return_value = inventory

        result = evaluator.evaluate_result_for_player(
            condition, WorldTick(0), _graph(), target_player_id=PlayerId(1),
        )

        expected = (
            PredicateReasonCode.MISSING_CONTEXT
            if reason == "missing"
            else PredicateReasonCode.UNSUPPORTED_PREDICATE
        )
        assert result.reason_code is expected
        assert result.failed_predicate is condition
        assert result.failed_path == ()

    def test_world_has_item_returns_unsupported_without_scanning_later_players(self) -> None:
        """共通核の未対応は後続playerで隠さず、元のHAS_ITEM条件へ即座に写す。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.unsupported(
            failed_predicate=MagicMock(), failed_path=(),
        )
        evaluator = _evaluator(predicate_evaluator=common)
        evaluator._player_status_repository.find_all.return_value = (
            MagicMock(player_id=PlayerId(1)),
            MagicMock(player_id=PlayerId(2)),
        )
        evaluator._player_inventory_repository.find_by_id.return_value = MagicMock()
        condition = _condition("HAS_ITEM", item_spec_id=1)

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator."
            "collect_owned_item_spec_ids_from_inventory",
            return_value=frozenset(),
        ):
            result = evaluator.evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.UNSUPPORTED_PREDICATE
        assert result.failed_predicate is condition
        assert common.evaluate.call_count == 1

    def test_world_has_item_prefers_later_match_over_common_missing(self) -> None:
        """先の共通評価が文脈不足でも、後のplayerが所持していれば成立する。"""
        common = MagicMock()
        common.evaluate.side_effect = (
            PredicateResult.context_missing(
                failed_predicate=MagicMock(),
                failed_path=(),
                required_context={"owned_item_spec_ids"},
            ),
            PredicateResult.satisfied(),
        )
        evaluator = _evaluator(predicate_evaluator=common)
        evaluator._player_status_repository.find_all.return_value = (
            MagicMock(player_id=PlayerId(1)),
            MagicMock(player_id=PlayerId(2)),
        )
        evaluator._player_inventory_repository.find_by_id.return_value = MagicMock()

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator."
            "collect_owned_item_spec_ids_from_inventory",
            return_value=frozenset(),
        ):
            result = evaluator.evaluate_result(
                _condition("HAS_ITEM", item_spec_id=1), WorldTick(0), _graph(),
            )

        assert result.is_satisfied

    def test_world_has_item_preserves_common_missing_without_match(self) -> None:
        """後続playerも未所持なら、先の共通評価の文脈不足を元DTOへ写す。"""
        common = MagicMock()
        common.evaluate.side_effect = (
            PredicateResult.context_missing(
                failed_predicate=MagicMock(),
                failed_path=(),
                required_context={"owned_item_spec_ids"},
            ),
            PredicateResult.not_satisfied(
                failed_predicate=MagicMock(), failed_path=(),
            ),
        )
        evaluator = _evaluator(predicate_evaluator=common)
        evaluator._player_status_repository.find_all.return_value = (
            MagicMock(player_id=PlayerId(1)),
            MagicMock(player_id=PlayerId(2)),
        )
        evaluator._player_inventory_repository.find_by_id.return_value = MagicMock()
        condition = _condition("HAS_ITEM", item_spec_id=1)

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator."
            "collect_owned_item_spec_ids_from_inventory",
            return_value=frozenset(),
        ):
            result = evaluator.evaluate_result(condition, WorldTick(0), _graph())

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.failed_predicate is condition
        assert result.missing_context == frozenset({"owned_item_spec_ids"})

    def test_world_has_item_prefers_later_match_over_missing_inventory(self) -> None:
        """先のplayerのinventoryが欠けても、後の所持者がいれば世界条件は成立する。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.satisfied()
        evaluator = _evaluator(predicate_evaluator=common)
        first = MagicMock(player_id=PlayerId(1))
        second = MagicMock(player_id=PlayerId(2))
        evaluator._player_status_repository.find_all.return_value = (first, second)
        known_inventory = MagicMock()
        evaluator._player_inventory_repository.find_by_id.side_effect = (
            None,
            known_inventory,
        )
        condition = _condition("HAS_ITEM", item_spec_id=1)

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator."
            "collect_owned_item_spec_ids_from_inventory",
            return_value=frozenset({ItemSpecId.create(1)}),
        ):
            result = evaluator.evaluate_result(condition, WorldTick(0), _graph())

        assert result.is_satisfied

    def test_world_has_item_reports_missing_when_known_players_do_not_match(self) -> None:
        """所持者がおらず一人でもinventoryが欠ける場合は通常未所持へ潰さない。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=MagicMock(),
            failed_path=(),
        )
        evaluator = _evaluator(predicate_evaluator=common)
        first = MagicMock(player_id=PlayerId(1))
        second = MagicMock(player_id=PlayerId(2))
        evaluator._player_status_repository.find_all.return_value = (first, second)
        evaluator._player_inventory_repository.find_by_id.side_effect = (
            None,
            MagicMock(),
        )
        condition = _condition("HAS_ITEM", item_spec_id=1)

        with patch(
            "ai_rpg_world.application.world_graph.scenario_condition_evaluator."
            "collect_owned_item_spec_ids_from_inventory",
            return_value=frozenset(),
        ):
            result = evaluator.evaluate_result(condition, WorldTick(0), _graph())

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


class TestProbabilityDiagnostics:
    """確率診断が短絡と乱数消費順を変えず、実際の判定値だけを保持する。"""

    def test_or_records_only_probability_leaf_that_was_evaluated(self) -> None:
        """先頭の通常未成立後に評価した確率条件だけを、根からの経路つきで返す。"""
        random_source = _CountingRandom(0.25)
        condition = _condition(
            "OR",
            children=(
                _condition("FLAG_SET", flag_name="not_set"),
                _condition("PROBABILITY", probability=0.5),
            ),
        )

        evaluation = _evaluator(random_source=random_source).evaluate_diagnostic(
            condition, WorldTick(0), _graph(),
        )

        assert evaluation.result.is_satisfied is True
        assert evaluation.probability_decisions[0].path == (1,)
        assert evaluation.probability_decisions[0].sampled_value == 0.25
        assert evaluation.probability_decisions[0].is_satisfied is True
        assert random_source.call_count == 1

    def test_short_circuited_probability_is_not_recorded_or_drawn(self) -> None:
        """ORの先頭成立で短絡された確率条件は診断にも載せず乱数も引かない。"""
        random_source = _CountingRandom(0.25)
        condition = _condition(
            "OR",
            children=(
                _condition("TICK_AT_LEAST", tick=0),
                _condition("PROBABILITY", probability=0.5),
            ),
        )

        evaluation = _evaluator(random_source=random_source).evaluate_diagnostic(
            condition, WorldTick(0), _graph(),
        )

        assert evaluation.result.is_satisfied is True
        assert evaluation.probability_decisions == ()
        assert random_source.call_count == 0

    def test_implicit_and_prefixes_probability_decision_path(self) -> None:
        """暗黙AND内の確率条件は条件番号を経路の先頭へ含める。"""
        random_source = _CountingRandom(0.75)

        evaluation = _evaluator(
            random_source=random_source
        ).evaluate_all_diagnostic(
            (
                _condition("TICK_AT_LEAST", tick=0),
                _condition("PROBABILITY", probability=0.5),
            ),
            WorldTick(0),
            _graph(),
        )

        assert evaluation.result.is_satisfied is False
        assert evaluation.probability_decisions[0].path == (1,)
        assert evaluation.probability_decisions[0].sampled_value == 0.75
