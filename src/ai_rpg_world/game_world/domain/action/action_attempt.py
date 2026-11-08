from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import ObjectId, PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


@final
@dataclass(frozen=True)
class LivingOnly:
    pass


@final
@dataclass(frozen=True)
class LivingOrDeparted:
    pass


ActorRequirement = LivingOnly | LivingOrDeparted


@final
@dataclass(frozen=True)
class WithPerson:
    person: PersonId


@final
@dataclass(frozen=True)
class WithObject:
    obj: ObjectId


@final
@dataclass(frozen=True)
class WithGroundItem:
    item: ItemInstanceId


CopresenceRequirement = WithPerson | WithObject | WithGroundItem


@final
@dataclass(frozen=True)
class UsesBody:
    pass


@final
@dataclass(frozen=True)
class DoesNotUseBody:
    pass


Exertion = UsesBody | DoesNotUseBody


class ActionAttempt(Protocol):
    @property
    def actor(self) -> PersonId: ...

    def kind(self) -> ActionKind: ...

    def actor_requirement(self) -> ActorRequirement: ...

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]: ...

    def exertion(self) -> Exertion: ...

    def person_as(self, kind: SubjectKind) -> PersonId: ...

    def this_item(self) -> ItemInstanceId: ...

    def acting_person(self) -> PersonId | NoActingPerson: ...

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId: ...

    def fall_cause_for(self, victim: PersonId) -> FallCause: ...

    def can_start_while_busy(self) -> bool: ...

    def is_allowed_in(self, stage: WorldStageDeclaration) -> bool: ...
