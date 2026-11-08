from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import CharacterDeclaration
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger


class SubjectKind(Enum):
    ACTOR = "ACTOR"
    TARGET = "TARGET"
    CHOSEN_BY_GROUP = "CHOSEN_BY_GROUP"
    NAMED_PERSON = "NAMED_PERSON"
    EACH_PERSON = "EACH_PERSON"


def _requiring(kind: SubjectKind) -> Requirements:
    return replace(Requirements.nothing(), subjects=frozenset({kind}))


@final
@dataclass(frozen=True)
class Actor:
    def person_in(self, trigger: Trigger) -> PersonId:
        return trigger.person_as(SubjectKind.ACTOR)

    def requirements(self) -> Requirements:
        return _requiring(SubjectKind.ACTOR)


@final
@dataclass(frozen=True)
class Target:
    def person_in(self, trigger: Trigger) -> PersonId:
        return trigger.person_as(SubjectKind.TARGET)

    def requirements(self) -> Requirements:
        return _requiring(SubjectKind.TARGET)


@final
@dataclass(frozen=True)
class ChosenByGroup:
    def person_in(self, trigger: Trigger) -> PersonId:
        return trigger.person_as(SubjectKind.CHOSEN_BY_GROUP)

    def requirements(self) -> Requirements:
        return _requiring(SubjectKind.CHOSEN_BY_GROUP)


@final
@dataclass(frozen=True)
class NamedPerson:
    character: CharacterDeclaration

    def person_in(self, trigger: Trigger) -> PersonId:
        return self.character.person_id

    def requirements(self) -> Requirements:
        return _requiring(SubjectKind.NAMED_PERSON)


@final
@dataclass(frozen=True)
class EachPerson:
    def person_in(self, trigger: Trigger) -> PersonId:
        return trigger.person_as(SubjectKind.EACH_PERSON)

    def requirements(self) -> Requirements:
        return _requiring(SubjectKind.EACH_PERSON)


Subject = Actor | Target | ChosenByGroup | NamedPerson | EachPerson


@final
@dataclass(frozen=True)
class ThisItem:
    def item_in(self, trigger: Trigger) -> ItemInstanceId:
        return trigger.this_item()


ItemSubject = ThisItem
