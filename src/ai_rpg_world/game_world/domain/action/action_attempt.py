from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import ObjectId, PersonId


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
