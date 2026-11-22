from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.being.contract import EnvironmentEntry, Introduction, Orientation
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.play_session_exception import (
    CastValidationException,
    PersonAlreadyBriefedException,
    PersonNotBriefedException,
    PersonNotCastException,
)


@final
@dataclass(frozen=True)
class CastMember:
    person: PersonId
    being_id: BeingId
    being_name: str

    def __post_init__(self) -> None:
        if not self.being_name.strip():
            raise CastValidationException(f"the Being cast as {self.person.value} has a blank name")


@final
@dataclass(frozen=True)
class Casting:
    beings: Mapping[PersonId, BeingId]

    def member(self, person: PersonId, being_name: str) -> CastMember:
        if person not in self.beings:
            raise PersonNotCastException(f"no Being is cast as {person.value}")
        return CastMember(person, self.beings[person], being_name)


@final
@dataclass(frozen=True)
class _Briefed:
    entry: EnvironmentEntry
    orientation: Orientation


@final
@dataclass(frozen=True)
class BeingCastInWorldEvent(DomainEvent):
    world: WorldId
    person: PersonId
    being_id: BeingId
    entry: EnvironmentEntry
    orientation: Orientation


class Cast(AggregateRoot[BeingCastInWorldEvent]):
    def __init__(self, world: WorldId, environment_name: str, members: Iterable[CastMember]) -> None:
        super().__init__()
        members = tuple(members)
        if not members:
            raise CastValidationException(f"cast for {world.value} has no members")
        if not environment_name.strip():
            raise CastValidationException(f"cast for {world.value} has a blank environment name")
        for label, values in (
            ("person", [m.person for m in members]),
            ("being", [m.being_id for m in members]),
            # 紹介は名前で渡すので、名前が重なると誰を紹介したかが分からない
            ("being name", [m.being_name for m in members]),
        ):
            repeated = sorted(str(v) for v, count in Counter(values).items() if count > 1)
            if repeated:
                raise CastValidationException(f"cast repeats a {label}: {repeated}")
        self._world = world
        self._environment_name = environment_name
        self._members = {m.person: m for m in members}
        self._briefed: dict[PersonId, _Briefed] = {}

    @property
    def world(self) -> WorldId:
        return self._world

    def people(self) -> tuple[PersonId, ...]:
        return tuple(self._members)

    def being_of(self, person: PersonId) -> BeingId:
        return self._member(person).being_id

    def brief(
        self, person: PersonId, *, orientation: Orientation, imposed_goal: str, known_people: Sequence[PersonId]
    ) -> None:
        member = self._member(person)
        if person in self._briefed:
            # 入った Being は最初の取り決めで入っているので、渡し直すと Being の受け取ったものと食い違う
            raise PersonAlreadyBriefedException(f"{person.value} has already been briefed in {self._world.value}")
        entry = EnvironmentEntry(
            environment_name=self._environment_name,
            imposed_goal=imposed_goal,
            introductions=tuple(Introduction(name=self._member(known).being_name) for known in known_people),
        )
        self._briefed[person] = _Briefed(entry, orientation)
        self.add_event(
            BeingCastInWorldEvent(
                **new_event_stamp(),
                world=self._world,
                person=person,
                being_id=member.being_id,
                entry=entry,
                orientation=orientation,
            )
        )

    def entry_of(self, person: PersonId) -> EnvironmentEntry:
        return self._briefing_of(person).entry

    def orientation_of(self, person: PersonId) -> Orientation:
        return self._briefing_of(person).orientation

    def _member(self, person: PersonId) -> CastMember:
        if person not in self._members:
            raise PersonNotCastException(f"{person.value} is not cast in {self._world.value}")
        return self._members[person]

    def _briefing_of(self, person: PersonId) -> _Briefed:
        self._member(person)
        if person not in self._briefed:
            raise PersonNotBriefedException(f"{person.value} has not been briefed in {self._world.value}")
        return self._briefed[person]


class CastRepository(Protocol):
    def get(self, world: WorldId) -> Cast: ...

    def save(self, cast: Cast) -> None: ...
