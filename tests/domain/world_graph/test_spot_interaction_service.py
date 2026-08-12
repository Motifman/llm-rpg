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
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import FlagSetPredicate
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
