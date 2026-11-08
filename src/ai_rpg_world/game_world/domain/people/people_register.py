from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.exception.people_register_exception import (
    CharacterListedTwiceException,
    PersonNotInRegisterException,
    PersonNotNamedException,
)
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId, WorldId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration


@final
@dataclass(frozen=True, kw_only=True)
class PersonNamedEvent(DomainEvent):
    world: WorldId
    person: PersonId
    name: DisplayName


@final
@dataclass(frozen=True)
class _RegisteredPerson:
    handle: PersonHandle
    appearance: DescriptionText


class PeopleRegister(AggregateRoot[PersonNamedEvent]):
    def __init__(self, world: WorldId, characters: Sequence[CharacterDeclaration]) -> None:
        super().__init__()
        self._world = world
        self._people: dict[PersonId, _RegisteredPerson] = {}
        self._names: dict[PersonId, DisplayName] = {}
        for number, character in enumerate(characters):
            if character.person_id in self._people:
                raise CharacterListedTwiceException(f"{character.person_id.value} is declared more than once")
            self._people[character.person_id] = _RegisteredPerson(PersonHandle(number), character.appearance)

    @classmethod
    def open(cls, world: WorldId, characters: Sequence[CharacterDeclaration]) -> PeopleRegister:
        return cls(world, characters)

    @property
    def world(self) -> WorldId:
        return self._world

    def name(self, person: PersonId, name: DisplayName) -> None:
        self._registered(person)
        if self._names.get(person) == name:
            return
        self._names[person] = name
        self.add_event(PersonNamedEvent(**new_event_stamp(), world=self._world, person=person, name=name))

    def handle_of(self, person: PersonId) -> PersonHandle:
        return self._registered(person).handle

    def name_of(self, person: PersonId) -> DisplayName:
        self._registered(person)
        if person not in self._names:
            raise PersonNotNamedException(f"{person.value} has not been named in the world {self._world.value}")
        return self._names[person]

    def appearance_of(self, person: PersonId) -> DescriptionText:
        return self._registered(person).appearance

    def _registered(self, person: PersonId) -> _RegisteredPerson:
        if person not in self._people:
            raise PersonNotInRegisterException(f"{person.value} is not in the register of {self._world.value}")
        return self._people[person]
