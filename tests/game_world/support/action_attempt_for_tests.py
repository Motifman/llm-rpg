from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson, fall_cause_from
from ai_rpg_world.game_world.domain.action.action_arguments import ActionArguments, TextArgumentValue
from ai_rpg_world.game_world.domain.action.action_attempt import (
    ActionAttempt,
    ActorRequirement,
    CopresenceRequirement,
    Exertion,
    LivingOnly,
    UsesBody,
)
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.world_stage_declaration import AllActionsAllowed
from ai_rpg_world.game_world.domain.exception.trigger_exception import (
    ArgumentNotInTriggerException,
    ItemNotInTriggerException,
    SubjectNotInTriggerException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


@final
@dataclass(frozen=True)
class ActionAttemptForTests(ActionAttempt):
    actor_id: PersonId
    target: PersonId | None = None
    item: ItemInstanceId | None = None
    arguments: ActionArguments = field(default_factory=lambda: MappingProxyType({}))
    action_kind: ActionKind = ActionKind.INTERACT_WITH_PERSON
    requirement: ActorRequirement = field(default_factory=LivingOnly)
    copresence: tuple[CopresenceRequirement, ...] = ()
    body_use: Exertion = field(default_factory=UsesBody)
    startable_while_busy: bool = False

    def __post_init__(self) -> None:
        arguments: Mapping[ArgumentName, TextArgumentValue | ItemInstanceId] = MappingProxyType(dict(self.arguments))
        object.__setattr__(self, "arguments", arguments)

    @property
    def actor(self) -> PersonId:
        return self.actor_id

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
            return self.actor_id
        if kind is SubjectKind.TARGET and self.target is not None:
            return self.target
        raise SubjectNotInTriggerException(f"{self!r} does not answer {kind.name}")

    def this_item(self) -> ItemInstanceId:
        if self.item is None:
            raise ItemNotInTriggerException(f"{self!r} does not answer the item")
        return self.item

    def acting_person(self) -> PersonId | NoActingPerson:
        return self.actor_id

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId:
        if name not in self.arguments:
            raise ArgumentNotInTriggerException(f"{self!r} does not answer the argument {name.value!r}")
        return self.arguments[name]

    def fall_cause_for(self, victim: PersonId) -> FallCause:
        return fall_cause_from(self.acting_person(), victim)

    def can_start_while_busy(self) -> bool:
        return self.startable_while_busy

    def is_allowed_in(self, stage: WorldStageDeclaration) -> bool:
        allowed = stage.allowed_actions
        return isinstance(allowed, AllActionsAllowed) or self.action_kind in allowed
