from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.exception.game_world_exception import require_distinct_memento_keys
from ai_rpg_world.game_world.domain.exception.world_records_exception import JointActionNotSettlingException
from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId, PersonId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.verb.joint_action_declaration import JointActionDeclaration
    from ai_rpg_world.game_world.domain.effect.effect import Effect


class JointActionSettlement(Enum):
    COMPLETED = auto()
    TIMED_OUT = auto()
    UNDECIDED = auto()

    def settles(self) -> bool:
        return self is not JointActionSettlement.UNDECIDED

    def effect_in(self, joint: JointActionDeclaration) -> Effect:
        if self is JointActionSettlement.COMPLETED:
            return joint.on_complete
        if self is JointActionSettlement.TIMED_OUT:
            return joint.on_timeout
        raise JointActionNotSettlingException(f"{joint.joint_id.value} has nothing to apply while undecided")


@final
@dataclass(frozen=True)
class JointActionPartDoneBy:
    obj: ObjectId
    interaction: InteractionId
    person: PersonId

    def part(self) -> tuple[ObjectId, InteractionId]:
        return (self.obj, self.interaction)


@final
@dataclass(frozen=True)
class JointActionProgress:
    joint: JointActionId
    started_at: WorldTick
    parts_done: frozenset[JointActionPartDoneBy]

    def __post_init__(self) -> None:
        require_distinct_memento_keys(
            [done.part() for done in self.parts_done],
            f"joint action {self.joint.value} has a part done by two people",
        )

    @classmethod
    def begin(
        cls, joint: JointActionId, part: tuple[ObjectId, InteractionId], by: PersonId, now: WorldTick
    ) -> JointActionProgress:
        return cls(joint, now, frozenset({JointActionPartDoneBy(*part, by)}))

    def with_part_done(self, part: tuple[ObjectId, InteractionId], by: PersonId) -> JointActionProgress:
        others = frozenset(done for done in self.parts_done if done.part() != part)
        return replace(self, parts_done=others | {JointActionPartDoneBy(*part, by)})

    def settlement(self, joint: JointActionDeclaration, now: WorldTick) -> JointActionSettlement:
        if self._is_complete(joint):
            return JointActionSettlement.COMPLETED
        if now.ticks_since(self.started_at) > joint.window:
            return JointActionSettlement.TIMED_OUT
        return JointActionSettlement.UNDECIDED

    def _is_complete(self, joint: JointActionDeclaration) -> bool:
        done_by = {done.part(): done.person for done in self.parts_done}
        if not all(part in done_by for part in joint.required):
            return False
        return not joint.distinct_people or len({done_by[part] for part in joint.required}) == len(joint.required)


@final
@dataclass(frozen=True)
class JointActionCompletedEvent(DomainEvent):
    world_id: WorldId
    joint_id: JointActionId
    at: WorldTick
    parts_done: frozenset[JointActionPartDoneBy]
    audience: frozenset[PersonId]
    refusal: RefusalCode | NoRefusal


@final
@dataclass(frozen=True)
class JointActionTimedOutEvent(DomainEvent):
    world_id: WorldId
    joint_id: JointActionId
    at: WorldTick
    parts_done: frozenset[JointActionPartDoneBy]
    audience: frozenset[PersonId]
    refusal: RefusalCode | NoRefusal
