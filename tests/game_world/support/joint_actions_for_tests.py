from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import HappeningNotice, NoNotice
from ai_rpg_world.game_world.domain.declaration.verb.joint_action_declaration import JointActionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.noun_interaction_declarations import ObjectInteractionDeclaration
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.value_object import InteractionId, Ticks
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from tests.game_world.support.verb_declarations_for_tests import pull_lever
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds, ChangesNothing
from tests.game_world.support.world_design_for_tests import obj

PUSH = InteractionId("push")


def levers_at(spot: str) -> tuple[ObjectDeclaration, ObjectDeclaration]:
    return obj("left_lever", spot), obj("right_lever", spot)


def pushing(
    levers: tuple[ObjectDeclaration, ...], precondition: Condition = AlwaysHolds()
) -> list[ObjectInteractionDeclaration]:
    push = replace(pull_lever(()), interaction_id=PUSH, precondition=precondition)
    return [ObjectInteractionDeclaration(obj=lever, interaction=push) for lever in levers]


def both_levers(
    levers: tuple[ObjectDeclaration, ObjectDeclaration],
    *,
    on_complete: Effect = ChangesNothing(),
    on_timeout: Effect = ChangesNothing(),
    complete_notice: HappeningNotice | NoNotice = NoNotice(),
    timeout_notice: HappeningNotice | NoNotice = NoNotice(),
) -> JointActionDeclaration:
    left, right = levers
    return JointActionDeclaration(
        joint_id=JointActionId("both_levers"),
        required=((left.object_id, PUSH), (right.object_id, PUSH)),
        window=Ticks(2),
        distinct_people=True,
        on_complete=on_complete,
        on_timeout=on_timeout,
        complete_notice=complete_notice,
        timeout_notice=timeout_notice,
    )
