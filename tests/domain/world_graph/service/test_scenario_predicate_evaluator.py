"""共通シナリオ述語の判定核が用途に依存しない意味を返す仕様。"""

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    EntityPlacementPredicateContext,
    OwnedItemSpecsPredicateContext,
    TickPredicateContext,
    WorldFlagPredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateReasonCode,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    EntityAtSpotPredicate,
    EntityCountAtSpotAtLeastPredicate,
    FlagSetPredicate,
    ItemSpecOwnedPredicate,
    TickAtLeastPredicate,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PredicateContextValidationException,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


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


class TestScenarioPredicateEvaluatorTickAtLeast:
    """tickの下限比較と評価入力不足の区別を保証する。"""

    @pytest.mark.parametrize(
        ("current", "threshold", "expected"),
        [(9, 10, False), (10, 10, True), (11, 10, True), (0, 0, True)],
    )
    def test_matches_at_or_after_threshold(
        self, current: int, threshold: int, expected: bool,
    ) -> None:
        """現在tickが閾値と等しい時点から成立し、それより前は成立しない。"""
        result = ScenarioPredicateEvaluator().evaluate(
            TickAtLeastPredicate(threshold),
            TickPredicateContext(WorldTick(current)),
        )

        assert result.is_satisfied is expected

    def test_missing_current_tick_is_context_missing(self) -> None:
        """現在tick未配線は通常未成立でなく、必要な文脈名を返す。"""
        result = ScenarioPredicateEvaluator().evaluate(
            TickAtLeastPredicate(10),
            TickPredicateContext(None),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"current_tick"})

    def test_wrong_context_kind_is_context_missing(self) -> None:
        """別用途の文脈を渡しても属性エラーにせず、current_tick不足を返す。"""
        result = ScenarioPredicateEvaluator().evaluate(
            TickAtLeastPredicate(10),
            WorldFlagPredicateContext(frozenset()),
        )

        assert result.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert result.missing_context == frozenset({"current_tick"})

    @pytest.mark.parametrize("current_tick", [0, "1", True])
    def test_context_rejects_non_world_tick(self, current_tick: object) -> None:
        """WorldTick以外を現在値として受け入れず、型の取り違えを早期発見する。"""
        with pytest.raises(PredicateContextValidationException):
            TickPredicateContext(current_tick)  # type: ignore[arg-type]


class TestScenarioPredicateEvaluatorLocation:
    """明示entity位置と通常entity在席数を同じ配置snapshotから評価する。"""

    def test_entity_at_spot_distinguishes_match_other_and_unplaced(self) -> None:
        """本人は一致時だけ成立し、別spotと未配置は通常不成立とする。"""
        entity_id = EntityId.create(1)
        target = SpotId.create(10)
        context = EntityPlacementPredicateContext(
            {entity_id: target, EntityId.create(2): SpotId.create(20)}
        )
        evaluator = ScenarioPredicateEvaluator()

        assert evaluator.evaluate(
            EntityAtSpotPredicate(entity_id, target), context,
        ).is_satisfied
        assert not evaluator.evaluate(
            EntityAtSpotPredicate(EntityId.create(2), target), context,
        ).is_satisfied
        result = evaluator.evaluate(
            EntityAtSpotPredicate(EntityId.create(3), target), context,
        )
        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED

    @pytest.mark.parametrize(
        ("required", "expected"), [(1, True), (2, True), (3, False)],
    )
    def test_entity_count_matches_at_threshold(
        self, required: int, expected: bool,
    ) -> None:
        """同じspotの通常entity数が閾値以上のときだけ成立する。"""
        target = SpotId.create(10)
        context = EntityPlacementPredicateContext(
            {
                EntityId.create(1): target,
                EntityId.create(99): target,
                EntityId.create(2): SpotId.create(20),
            }
        )

        result = ScenarioPredicateEvaluator().evaluate(
            EntityCountAtSpotAtLeastPredicate(target, required), context,
        )

        assert result.is_satisfied is expected

    @pytest.mark.parametrize(
        "predicate",
        [
            EntityAtSpotPredicate(EntityId.create(1), SpotId.create(1)),
            EntityCountAtSpotAtLeastPredicate(SpotId.create(1), 1),
        ],
    )
    def test_location_predicates_distinguish_empty_and_missing_context(
        self, predicate: object,
    ) -> None:
        """空配置は通常未成立、未配線と異種contextは文脈不足として返す。"""
        evaluator = ScenarioPredicateEvaluator()
        empty = evaluator.evaluate(  # type: ignore[arg-type]
            predicate, EntityPlacementPredicateContext({}),
        )
        missing = evaluator.evaluate(  # type: ignore[arg-type]
            predicate, EntityPlacementPredicateContext(None),
        )
        wrong = evaluator.evaluate(  # type: ignore[arg-type]
            predicate, TickPredicateContext(WorldTick(0)),
        )

        assert empty.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert missing.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert wrong.missing_context == frozenset({"entity_locations"})

    def test_context_copies_and_validates_entity_locations(self) -> None:
        """配置mappingを防御コピーし、不正なID型や値型を拒否する。"""
        source = {EntityId.create(1): SpotId.create(1)}
        context = EntityPlacementPredicateContext(source)
        source[EntityId.create(2)] = SpotId.create(2)

        assert len(context.entity_locations or {}) == 1
        with pytest.raises(PredicateContextValidationException):
            EntityPlacementPredicateContext({1: SpotId.create(1)})  # type: ignore[dict-item]


class TestScenarioPredicateEvaluatorItemOwnership:
    """品目所持の完全一致と、空所持・文脈不足の区別を保証する。"""

    def test_matches_only_owned_item_spec(self) -> None:
        """指定品目が解決済み所持集合に含まれるときだけ成立する。"""
        owned = ItemSpecId.create(1)
        context = OwnedItemSpecsPredicateContext(frozenset({owned}))
        evaluator = ScenarioPredicateEvaluator()

        assert evaluator.evaluate(ItemSpecOwnedPredicate(owned), context).is_satisfied
        result = evaluator.evaluate(
            ItemSpecOwnedPredicate(ItemSpecId.create(2)), context,
        )
        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED

    def test_empty_set_is_normal_unsatisfied(self) -> None:
        """空集合は所持情報が配線済みなので、通常未成立として返す。"""
        result = ScenarioPredicateEvaluator().evaluate(
            ItemSpecOwnedPredicate(ItemSpecId.create(1)),
            OwnedItemSpecsPredicateContext(frozenset()),
        )

        assert result.reason_code is PredicateReasonCode.NOT_SATISFIED
        assert result.missing_context == frozenset()

    def test_missing_or_wrong_context_reports_owned_item_specs(self) -> None:
        """所持集合の未配線と異種文脈は、必要な文脈名つきで返す。"""
        predicate = ItemSpecOwnedPredicate(ItemSpecId.create(1))
        evaluator = ScenarioPredicateEvaluator()
        missing = evaluator.evaluate(
            predicate, OwnedItemSpecsPredicateContext(None),
        )
        wrong = evaluator.evaluate(
            predicate, WorldFlagPredicateContext(frozenset()),
        )

        assert missing.reason_code is PredicateReasonCode.MISSING_CONTEXT
        assert missing.missing_context == frozenset({"owned_item_spec_ids"})
        assert wrong.missing_context == frozenset({"owned_item_spec_ids"})

    @pytest.mark.parametrize(
        "owned_item_spec_ids",
        [set(), frozenset({1}), frozenset({"1"})],
    )
    def test_context_rejects_mutable_or_untyped_collections(
        self, owned_item_spec_ids: object,
    ) -> None:
        """可変集合とItemSpecId以外の要素を拒否し、評価中の意味変化を防ぐ。"""
        with pytest.raises(PredicateContextValidationException):
            OwnedItemSpecsPredicateContext(owned_item_spec_ids)  # type: ignore[arg-type]
