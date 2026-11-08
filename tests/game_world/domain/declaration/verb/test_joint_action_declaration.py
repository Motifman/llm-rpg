from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.action.trigger import JointActionCompleted
from ai_rpg_world.game_world.domain.declaration.verb import JointActionDeclaration, NoNotice
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    DuplicateJointActionPartException,
    NoJointActionPartsException,
)
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, Ticks
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from tests.game_world.domain.declaration.verb.verb_parts import ChangesNothing

_OPEN_VALVE_A = (ObjectId("valve_a"), InteractionId("open_valve"))
_OPEN_VALVE_B = (ObjectId("valve_b"), InteractionId("open_valve"))


def _joint_action(required: tuple[tuple[ObjectId, InteractionId], ...]) -> JointActionDeclaration:
    return JointActionDeclaration(
        joint_id=JointActionId("open_both_valves"),
        required=required,
        window=Ticks(3),
        distinct_people=True,
        on_complete=ChangesNothing(),
        on_timeout=ChangesNothing(),
        complete_notice=NoNotice(),
        timeout_notice=NoNotice(),
    )


class TestJointActionDeclarationRequired:
    """JointActionDeclaration が、揃えるべき操作の並びとして意味のある宣言だけを作ることを保証する。"""

    def test_empty_required_raises(self) -> None:
        """required が空だと、揃えるものが無いので NoJointActionPartsException を投げる。"""
        with pytest.raises(NoJointActionPartsException):
            _joint_action(required=())

    def test_same_object_and_interaction_twice_raises(self) -> None:
        """required に同じ (物体, 操作) の組を 2 回書くと、書き間違いとして DuplicateJointActionPartException を投げる。"""
        with pytest.raises(DuplicateJointActionPartException):
            _joint_action(required=(_OPEN_VALVE_A, _OPEN_VALVE_A))

    def test_distinct_parts_are_kept_in_the_written_order(self) -> None:
        """required に別々の組を書くと、断らずに書いた順のまま持つ。"""
        joint = _joint_action(required=(_OPEN_VALVE_A, _OPEN_VALVE_B))

        assert joint.required == (_OPEN_VALVE_A, _OPEN_VALVE_B)


class TestJointActionDeclarationAsTrigger:
    """JointActionDeclaration が、二人で合わせる操作が揃ったきっかけにそのまま入ることを保証する。"""

    def test_completed_trigger_answers_the_declared_joint_id(self) -> None:
        """JointActionCompleted に宣言を包むと、きっかけから宣言の joint_id が読める。"""
        trigger = JointActionCompleted(joint=_joint_action(required=(_OPEN_VALVE_A, _OPEN_VALVE_B)))

        assert trigger.joint.joint_id == JointActionId("open_both_valves")
