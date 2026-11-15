from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode

from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import HappeningNotice, NoNotice
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    DuplicateJointActionPartException,
    NoJointActionPartsException,
)
from ai_rpg_world.game_world.domain.perception import Stimulus
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, PersonId, Ticks, WorldTick
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.world_records.joint_action_progress import JointActionSettlement


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

    def stimuli_when_settled(
        self,
        settlement: JointActionSettlement,
        refusal: RefusalCode | NoRefusal,
        audience: frozenset[PersonId],
        at: WorldTick,
    ) -> tuple[Stimulus, ...]:
        # 断られた効果は巻き戻っていて、世界では何も起きていない。
        if isinstance(refusal, RefusalCode):
            return ()
        return settlement.notice_in(self).stimuli(audience, at)
