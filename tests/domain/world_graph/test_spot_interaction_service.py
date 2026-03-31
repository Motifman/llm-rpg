from __future__ import annotations

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
    UnknownSpotObjectException,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
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
                            effect_type=InteractionEffectTypeEnum.CHANGE_CONNECTION_STATE,
                            parameters={"connection_id": 5, "is_passable": True},
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
        assert r.connection_passability_updates == ((ConnectionId.create(5), True),)
