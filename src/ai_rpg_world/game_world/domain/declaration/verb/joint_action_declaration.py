from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import HappeningNotice, NoNotice
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    DuplicateJointActionPartException,
    NoJointActionPartsException,
)
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, Ticks
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId


@final
@dataclass(frozen=True)
class JointActionDeclaration:
    joint_id: JointActionId
    required: tuple[tuple[ObjectId, InteractionId], ...]
    window: Ticks
    distinct_people: bool
    on_complete: Effect
    on_timeout: Effect
    complete_notice: HappeningNotice | NoNotice
    timeout_notice: HappeningNotice | NoNotice

    def __post_init__(self) -> None:
        if not self.required:
            raise NoJointActionPartsException(f"JointActionDeclaration {self.joint_id.value} requires no interaction")
        if len(set(self.required)) != len(self.required):
            raise DuplicateJointActionPartException(
                f"JointActionDeclaration {self.joint_id.value} requires the same interaction on the same object twice"
            )
