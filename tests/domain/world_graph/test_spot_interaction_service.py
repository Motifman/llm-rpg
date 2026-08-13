from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
    ScenarioPredicateEvaluationException,
    UnknownSpotObjectException,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
    ItemSpecCountAtLeastPredicate,
    StateValuesMatchPredicate,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _door_object() -> SpotObject:
    key = ItemSpecId.create(99)
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="Door",
        description="",
        object_type=SpotObjectTypeEnum.DOOR,
        state={"open": False},
        interactions=(
            InteractionDef(
                action_name="open",
                display_label="開ける",
                preconditions=(
                    InteractionCondition(
                        condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                        target_item_spec_id=key,
                        failure_message="鍵が要る",
                    ),
                ),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                        parameters={"state_updates": {"open": True}},
                    ),
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                        parameters={"message": "開いた"},
                    ),
                ),
            ),
        ),
    )


def _make_interior(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestSpotInteractionService:
    @pytest.mark.parametrize(
        ("condition_type", "required_item_spec_ids"),
        [
            (InteractionConditionTypeEnum.HAS_ITEM, None),
            (InteractionConditionTypeEnum.HAS_ITEMS, (ItemSpecId.create(7),)),
        ],
    )
    def test_quantity_conditions_delegate_to_shared_predicate_evaluator(
        self,
        condition_type: InteractionConditionTypeEnum,
        required_item_spec_ids: tuple[ItemSpecId, ...] | None,
    ) -> None:
        """行為者の数量条件は品目別個数と必要数を共通評価核へ渡す。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = PredicateResult.satisfied()
        item_spec_id = ItemSpecId.create(7)
        condition = InteractionCondition(
            condition_type=condition_type,
            target_item_spec_id=(
                item_spec_id
                if condition_type is InteractionConditionTypeEnum.HAS_ITEM
                else None
            ),
            required_item_spec_ids=required_item_spec_ids,
            required_quantity=2,
        )
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        result = SpotInteractionService(
            predicate_evaluator=evaluator,
        ).evaluate_preconditions_result(
            interaction,
            _door_object(),
            frozenset({item_spec_id}),
            frozenset(),
            owned_item_spec_counts={item_spec_id: 2},
        )

        assert result.is_satisfied
        predicate, context = evaluator.evaluate.call_args.args
        assert predicate == ItemSpecCountAtLeastPredicate(item_spec_id, 2)
        assert context.item_spec_counts == {item_spec_id: 2}

    def test_has_items_evaluates_specs_in_declared_order(self) -> None:
        """HAS_ITEMSは宣言順に各品目を評価し、最初の不足で元条件を返す。"""
        evaluator = MagicMock()
        first = ItemSpecId.create(1)
        second = ItemSpecId.create(2)
        evaluator.evaluate.side_effect = [
            PredicateResult.satisfied(),
            PredicateResult.not_satisfied(
                failed_predicate=ItemSpecCountAtLeastPredicate(second, 2),
                failed_path=(),
            ),
        ]
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
            required_item_spec_ids=(first, second),
            required_quantity=2,
            failure_message="材料が足りない",
        )
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        result = SpotInteractionService(
            predicate_evaluator=evaluator,
        ).evaluate_preconditions_result(
            interaction,
            _door_object(),
            frozenset({first, second}),
            frozenset(),
            owned_item_spec_counts={first: 2, second: 1},
        )

        assert not result.is_satisfied
        assert result.failed_predicate is condition
        assert result.failed_path == (0,)
        assert result.failure_message == "材料が足りない"
        assert [
            call.args[0].item_spec_id for call in evaluator.evaluate.call_args_list
        ] == [first, second]

    def test_has_items_keeps_duplicate_specs_as_independent_checks(self) -> None:
        """重複品目は個数を合算せず、従来どおり同じ必要数を二度判定する。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = PredicateResult.satisfied()
        item_spec_id = ItemSpecId.create(1)
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
            required_item_spec_ids=(item_spec_id, item_spec_id),
            required_quantity=2,
        )
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        result = SpotInteractionService(
            predicate_evaluator=evaluator,
        ).evaluate_preconditions_result(
            interaction,
            _door_object(),
            frozenset({item_spec_id}),
            frozenset(),
            owned_item_spec_counts={item_spec_id: 2},
        )

        assert result.is_satisfied
        assert evaluator.evaluate.call_count == 2
        assert all(
            call.args[0] == ItemSpecCountAtLeastPredicate(item_spec_id, 2)
            for call in evaluator.evaluate.call_args_list
        )

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    @pytest.mark.parametrize(
        "condition_type",
        [InteractionConditionTypeEnum.HAS_ITEM, InteractionConditionTypeEnum.HAS_ITEMS],
    )
    def test_quantity_evaluation_failure_stops_interaction(
        self,
        reason: str,
        condition_type: InteractionConditionTypeEnum,
    ) -> None:
        """数量共通核の入力不足・未対応を通常の所持不足へ縮退させない。"""
        item_spec_id = ItemSpecId.create(7)
        failed = ItemSpecCountAtLeastPredicate(item_spec_id, 1)
        evaluator = MagicMock()
        evaluator.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"item_spec_counts"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(
                failed_predicate=failed, failed_path=(),
            )
        )
        condition = InteractionCondition(
            condition_type=condition_type,
            target_item_spec_id=(
                item_spec_id
                if condition_type is InteractionConditionTypeEnum.HAS_ITEM
                else None
            ),
            required_item_spec_ids=(
                (item_spec_id,)
                if condition_type is InteractionConditionTypeEnum.HAS_ITEMS
                else None
            ),
        )
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotInteractionService(
                predicate_evaluator=evaluator,
            ).evaluate_preconditions_result(
                interaction,
                _door_object(),
                frozenset({item_spec_id}),
                frozenset(),
                owned_item_spec_counts={item_spec_id: 1},
            )

    @pytest.mark.parametrize(
        "condition",
        [
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
                required_item_spec_ids=(),
            ),
        ],
    )
    def test_invalid_quantity_definition_does_not_call_shared_evaluator(
        self, condition: InteractionCondition,
    ) -> None:
        """参照品目がない旧DTOは従来文面で不成立となり、共通核へ渡さない。"""
        evaluator = MagicMock()
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        result = SpotInteractionService(
            predicate_evaluator=evaluator,
        ).evaluate_preconditions_result(
            interaction, _door_object(), frozenset(), frozenset(),
        )

        assert not result.is_satisfied
        evaluator.evaluate.assert_not_called()

    @pytest.mark.parametrize(
        "condition",
        [
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                target_item_spec_id=ItemSpecId.create(7),
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
                required_item_spec_ids=(ItemSpecId.create(7),),
            ),
        ],
    )
    def test_quantity_one_without_counts_uses_owned_spec_fallback(
        self, condition: InteractionCondition,
    ) -> None:
        """数量1の両条件は個数mapping省略時も所持品目集合から各1個へ戻す。"""
        item_spec_id = ItemSpecId.create(7)
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        result = SpotInteractionService().evaluate_preconditions_result(
            interaction,
            _door_object(),
            frozenset({item_spec_id}),
            frozenset(),
        )

        assert result.is_satisfied

    @pytest.mark.parametrize(
        "condition",
        [
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                target_item_spec_id=ItemSpecId.create(7),
                required_quantity=2,
            ),
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.HAS_ITEMS,
                required_item_spec_ids=(ItemSpecId.create(7),),
                required_quantity=2,
            ),
        ],
    )
    def test_quantity_above_one_without_counts_fails_before_evaluation(
        self, condition: InteractionCondition,
    ) -> None:
        """数量2以上の両条件は個数mapping省略を推測せず、評価前に即時停止する。"""
        interaction = InteractionDef(
            action_name="craft", display_label="作る",
            preconditions=(condition,), effects=(),
        )

        with pytest.raises(ValueError, match="owned_item_spec_counts is required"):
            SpotInteractionService().evaluate_preconditions_result(
                interaction,
                _door_object(),
                frozenset({ItemSpecId.create(7)}),
                frozenset(),
            )

    def test_object_state_delegates_and_keeps_failure_contract(self) -> None:
        """OBJECT_STATEは共通核へ委譲し、元条件・経路・作者文面を維持する。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=StateValuesMatchPredicate({"open": True}),
            failed_path=(),
        )
        service = SpotInteractionService(predicate_evaluator=evaluator)
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
            required_state={"open": True},
            failure_message="まだ閉じている",
        )
        interaction = InteractionDef(
            action_name="enter", display_label="入る",
            preconditions=(condition,), effects=(),
        )

        result = service.evaluate_preconditions_result(
            interaction, _door_object(), frozenset(), frozenset(),
        )

        assert result.is_satisfied is False
        assert result.failure_message == "まだ閉じている"
        assert result.failed_predicate is condition
        assert result.failed_path == (0,)
        predicate, context = evaluator.evaluate.call_args.args
        assert dict(predicate.required_values) == {"open": True}
        assert dict(context.state_values) == {"open": False}

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_object_state_evaluation_failure_stops_interaction(
        self, reason: str,
    ) -> None:
        """state共通核の入力不足・未対応を通常の操作不可へ縮退させない。"""
        evaluator = MagicMock()
        failed = StateValuesMatchPredicate({"open": True})
        evaluator.evaluate.return_value = (
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
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
            required_state={"open": True},
        )
        interaction = InteractionDef(
            action_name="enter", display_label="入る",
            preconditions=(condition,), effects=(),
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotInteractionService(
                predicate_evaluator=evaluator,
            ).evaluate_preconditions_result(
                interaction, _door_object(), frozenset(), frozenset(),
            )

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    @pytest.mark.parametrize(
        ("condition_type", "context_kwarg"),
        [
            (InteractionConditionTypeEnum.ITEM_INSTANCE_STATE, "acting_item_aggregate"),
            (
                InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE,
                "target_item_aggregate",
            ),
            (InteractionConditionTypeEnum.PLAYER_STATE_IS, "acting_player_status"),
            (
                InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
                "target_player_status",
            ),
        ],
    )
    def test_scoped_state_evaluation_failure_stops_interaction(
        self,
        reason: str,
        condition_type: InteractionConditionTypeEnum,
        context_kwarg: str,
    ) -> None:
        """item/playerの使う側・使われる側も評価不能を通常falseへ縮退させない。"""
        evaluator = MagicMock()
        failed = StateValuesMatchPredicate({"ready": True})
        evaluator.evaluate.return_value = (
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
        condition = InteractionCondition(
            condition_type=condition_type,
            required_state={"ready": True},
        )
        interaction = InteractionDef(
            action_name="use", display_label="使う",
            preconditions=(condition,), effects=(),
        )
        scoped_aggregate = MagicMock(state={"ready": False})

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotInteractionService(
                predicate_evaluator=evaluator,
            ).evaluate_preconditions_result(
                interaction,
                _door_object(),
                frozenset(),
                frozenset(),
                **{context_kwarg: scoped_aggregate},
            )

    def test_flag_set_delegates_to_shared_predicate_evaluator(self):
        """FLAG_SET は共通評価核へ一度だけ委譲し、既存の失敗文を維持する。"""
        evaluator = MagicMock()
        evaluator.evaluate.return_value = PredicateResult.not_satisfied(
            failed_predicate=FlagSetPredicate("power_on"),
            failed_path=(),
        )
        service = SpotInteractionService(predicate_evaluator=evaluator)
        interaction = InteractionDef(
            action_name="open",
            display_label="開ける",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.FLAG_SET,
                    flag_name="power_on",
                    failure_message="電源が入っていない",
                ),
            ),
            effects=(),
        )

        result = service.evaluate_preconditions_result(
            interaction,
            None,
            frozenset(),
            frozenset(),
        )

        assert result.is_satisfied is False
        assert result.failure_message == "電源が入っていない"
        assert result.failed_predicate is interaction.preconditions[0]
        assert result.failed_path == (0,)
        evaluator.evaluate.assert_called_once()

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_flag_set_evaluation_failure_stops_interaction(self, reason):
        """共通評価核の入力不足・未対応は、操作不可という通常結果へ縮退させない。"""
        evaluator = MagicMock()
        failed = FlagSetPredicate("power_on")
        evaluator.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"world_flags"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(
                failed_predicate=failed,
                failed_path=(),
            )
        )
        interaction = InteractionDef(
            action_name="open",
            display_label="開ける",
            preconditions=(InteractionCondition(
                condition_type=InteractionConditionTypeEnum.FLAG_SET,
                flag_name="power_on",
            ),),
            effects=(),
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotInteractionService(
                predicate_evaluator=evaluator
            ).evaluate_preconditions_result(
                interaction, None, frozenset(), frozenset(),
            )

    def test_execute_open_success(self):
        interior = _make_interior(_door_object())
        svc = SpotInteractionService()
        r = svc.execute_interaction(
            interior,
            SpotObjectId.create(1),
            "open",
            frozenset({ItemSpecId.create(99)}),
            frozenset(),
        )
        assert r.new_interior.get_object(SpotObjectId.create(1)).state["open"] is True
        assert "開いた" in r.messages
        assert r.new_flags == frozenset()
        assert r.action_display_label == "開ける"

    def test_blank_display_label_falls_back_to_action_name(self):
        """loaderを迂回した空ラベルでも、結果表示は落ちずaction_nameへ戻る。"""
        obj = SpotObject(
            object_id=SpotObjectId.create(2),
            name="操作盤",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="inspect_panel",
                    display_label="  ",
                    preconditions=(),
                    effects=(),
                ),
            ),
        )

        result = SpotInteractionService().execute_interaction(
            _make_interior(obj),
            SpotObjectId.create(2),
            "inspect_panel",
            frozenset(),
            frozenset(),
        )

        assert result.action_display_label == "inspect_panel"

    def test_execute_without_key_raises(self):
        interior = _make_interior(_door_object())
        svc = SpotInteractionService()
        with pytest.raises(InteractionNotAllowedException):
            svc.execute_interaction(
                interior,
                SpotObjectId.create(1),
                "open",
                frozenset(),
                frozenset(),
            )

    def test_unknown_object_raises(self):
        svc = SpotInteractionService()
        with pytest.raises(UnknownSpotObjectException):
            svc.execute_interaction(
                SpotInterior.empty(),
                SpotObjectId.create(1),
                "open",
                frozenset(),
                frozenset(),
            )

    def test_unknown_action_raises(self):
        interior = _make_interior(_door_object())
        svc = SpotInteractionService()
        with pytest.raises(InteractionNotFoundException):
            svc.execute_interaction(
                interior,
                SpotObjectId.create(1),
                "kick",
                frozenset({ItemSpecId.create(99)}),
                frozenset(),
            )

    def test_set_flag_and_connection(self):
        obj = SpotObject(
            object_id=SpotObjectId.create(2),
            name="Switch",
            description="",
            object_type=SpotObjectTypeEnum.SWITCH,
            state={},
            interactions=(
                InteractionDef(
                    action_name="use",
                    display_label="押す",
                    preconditions=(InteractionCondition(condition_type=InteractionConditionTypeEnum.ALWAYS),),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.SET_FLAG,
                            parameters={"flag_name": "power_on"},
                        ),
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE,
                            parameters={"connection_id": 5, "new_state": "OPEN"},
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(obj)
        svc = SpotInteractionService()
        r = svc.execute_interaction(
            interior,
            SpotObjectId.create(2),
            "use",
            frozenset(),
            frozenset(),
        )
        assert "power_on" in r.new_flags
        assert len(r.passage_state_updates) == 1
        spec = r.passage_state_updates[0]
        assert spec.connection_id == 5
        assert spec.new_state == "OPEN"

    def test_change_object_state_can_target_other_object(self):
        switch = SpotObject(
            object_id=SpotObjectId.create(10),
            name="Switch",
            description="",
            object_type=SpotObjectTypeEnum.SWITCH,
            state={"on": False},
            interactions=(
                InteractionDef(
                    action_name="toggle",
                    display_label="切り替える",
                    preconditions=(InteractionCondition(condition_type=InteractionConditionTypeEnum.ALWAYS),),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                            parameters={
                                "object_id": 11,
                                "state_updates": {"open": True},
                            },
                        ),
                    ),
                ),
            ),
        )
        door = SpotObject(
            object_id=SpotObjectId.create(11),
            name="Door",
            description="",
            object_type=SpotObjectTypeEnum.DOOR,
            state={"open": False},
            interactions=(),
        )
        interior = SpotInterior((), (switch, door), (), ())
        svc = SpotInteractionService()
        result = svc.execute_interaction(
            interior,
            SpotObjectId.create(10),
            "toggle",
            frozenset(),
            frozenset(),
        )
        updated_door = result.new_interior.get_object(SpotObjectId.create(11))
        assert updated_door is not None
        assert updated_door.state["open"] is True

    def test_object_state_precondition_reads_the_explicit_target_object(self):
        """OBJECT_STATE は操作元でなく target_object に宣言した物体の状態を読む。"""
        switch = SpotObject(
            object_id=SpotObjectId.create(20),
            name="Switch",
            description="",
            object_type=SpotObjectTypeEnum.SWITCH,
            state={"armed": False},
            interactions=(
                InteractionDef(
                    action_name="release_lock",
                    display_label="固定を外す",
                    preconditions=(
                        InteractionCondition(
                            condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
                            target_object_id=SpotObjectId.create(21),
                            required_state={"armed": True},
                            failure_message="対象が準備されていない",
                        ),
                    ),
                    effects=(),
                ),
            ),
        )
        target = SpotObject(
            object_id=SpotObjectId.create(21),
            name="Remote lock",
            description="",
            object_type=SpotObjectTypeEnum.OTHER,
            state={"armed": True},
            interactions=(),
        )

        result = SpotInteractionService().execute_interaction(
            SpotInterior((), (switch, target), (), ()),
            SpotObjectId.create(20),
            "release_lock",
            frozenset(),
            frozenset(),
        )

        assert result.action_display_label == "固定を外す"
