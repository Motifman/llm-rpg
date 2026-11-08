from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.exception.person_exception import (
    OutcomeAlreadyDecidedException,
    PersonListedTwiceException,
    PersonNotInWorldException,
)
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId


@final
@dataclass(frozen=True)
class Died:
    pass


@final
@dataclass(frozen=True)
class DeclaredOutcome:
    outcome: OutcomeDeclaration


Outcome = Died | DeclaredOutcome


@final
@dataclass(frozen=True)
class Undecided:
    pass


@dataclass(frozen=True, kw_only=True)
class PersonOutcomeDecidedEvent(DomainEvent):
    world: WorldId
    person: PersonId
    outcome: Outcome


class PersonOutcomes(AggregateRoot[PersonOutcomeDecidedEvent]):
    def __init__(self, world: WorldId, people: tuple[PersonId, ...]) -> None:
        super().__init__()
        self._world = world
        self._outcomes: dict[PersonId, Outcome | Undecided] = {person: Undecided() for person in people}

    @classmethod
    def start(cls, world: WorldId, people: tuple[PersonId, ...]) -> PersonOutcomes:
        if len(set(people)) != len(people):
            raise PersonListedTwiceException(f"people must be distinct, got {[p.value for p in people]}")
        return cls(world, people)

    @property
    def world(self) -> WorldId:
        return self._world

    def decide(self, person: PersonId, outcome: Outcome) -> None:
        current = self.outcome_of(person)
        if not isinstance(current, Undecided):
            raise OutcomeAlreadyDecidedException(f"{person.value} already has the outcome {current}")
        self._outcomes[person] = outcome
        self.add_event(
            PersonOutcomeDecidedEvent(
                **new_event_stamp(),
                world=self._world,
                person=person,
                outcome=outcome,
            )
        )

    def outcome_of(self, person: PersonId) -> Outcome | Undecided:
        if person not in self._outcomes:
            raise PersonNotInWorldException(f"{person.value} is not in the world {self._world.value}")
        return self._outcomes[person]

    def all_decided(self) -> bool:
        return not self.undecided_people()

    def undecided_people(self) -> tuple[PersonId, ...]:
        return tuple(person for person, outcome in self._outcomes.items() if isinstance(outcome, Undecided))
