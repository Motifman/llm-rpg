from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActionAttempt,
    ActorRequirement,
    CopresenceRequirement,
    Exertion,
    LivingOnly,
    UsesBody,
)
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class ActionAttemptForTests(ActionAttempt):
    acting_person: PersonId
    target: PersonId | None = None
    item: ItemInstanceId | None = None
    action_kind: ActionKind = ActionKind.INTERACT_WITH_PERSON
    requirement: ActorRequirement = field(default_factory=LivingOnly)
    copresence: tuple[CopresenceRequirement, ...] = ()
    body_use: Exertion = field(default_factory=UsesBody)

    @property
    def actor(self) -> PersonId:
        return self.acting_person

    def kind(self) -> ActionKind:
        return self.action_kind

    def actor_requirement(self) -> ActorRequirement:
        return self.requirement

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]:
        return self.copresence

    def exertion(self) -> Exertion:
        return self.body_use

    def person_as(self, kind: SubjectKind) -> PersonId:
        if kind is SubjectKind.ACTOR:
            return self.acting_person
        if kind is SubjectKind.TARGET and self.target is not None:
            return self.target
        raise SubjectNotInTriggerException(f"{self!r} does not answer {kind.name}")

    def this_item(self) -> ItemInstanceId:
        if self.item is None:
            raise ItemNotInTriggerException(f"{self!r} does not answer the item")
        return self.item
