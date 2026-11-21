from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.exception.game_world_exception import MementoDoesNotMatchDesignException
from ai_rpg_world.game_world.domain.exception.person_exception import (
    OutcomeAlreadyDecidedException,
    PersonListedTwiceException,
    PersonNotInWorldException,
)
from ai_rpg_world.game_world.domain.value_object import OutcomeId, PersonId, WorldId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
    from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
    from ai_rpg_world.game_world.domain.perception.stimulus import Stimulus
    from ai_rpg_world.game_world.domain.world_records.missed_notices import MissedNotices


@final
@dataclass(frozen=True)
class Died:
    def announced_to(self, person: PersonId, at: WorldTick) -> tuple[Stimulus, ...]:
        # 死んだ結末には作者の文が無いので、結末の知らせを出さない (D2203)。
        return ()

    def notices_on_leaving(self, missed: MissedNotices, at: WorldTick) -> tuple[Perceived, ...]:
        # 死んだ人は世界から外れないので、たまった知らせを外れるときに渡さない。
        return ()

    def forget_notices_on_leaving(self, missed: MissedNotices) -> None:
        pass


@final
@dataclass(frozen=True)
class DeclaredOutcome:
    outcome: OutcomeDeclaration

    def announced_to(self, person: PersonId, at: WorldTick) -> tuple[Stimulus, ...]:
        return (self.outcome.announcement_to(person, at),)

    def notices_on_leaving(self, missed: MissedNotices, at: WorldTick) -> tuple[Perceived, ...]:
        # 気を失ったまま外れた人は目覚めないので、目が覚めたときと同じ順で、外れるときに渡す (D2203)。
        return missed.perceived_on_waking(at)

    def forget_notices_on_leaving(self, missed: MissedNotices) -> None:
        missed.clear()


Outcome = Died | DeclaredOutcome


@final
@dataclass(frozen=True)
class Undecided:
    pass


@final
@dataclass(frozen=True)
class OutcomeOfPerson:
    person: PersonId
    outcome: Died | OutcomeId | Undecided


@final
@dataclass(frozen=True)
class PersonOutcomesMemento:
    world_id: WorldId
    outcomes: tuple[OutcomeOfPerson, ...]


@dataclass(frozen=True, kw_only=True)
class PersonOutcomeDecidedEvent(DomainEvent):
    world: WorldId
    person: PersonId
    outcome: Outcome
    at: WorldTick


class PersonOutcomes(AggregateRoot[PersonOutcomeDecidedEvent]):
    def __init__(self, world: WorldId, outcomes: tuple[tuple[PersonId, Outcome | Undecided], ...]) -> None:
        super().__init__()
        people = [person for person, _ in outcomes]
        if len(set(people)) != len(people):
            raise PersonListedTwiceException(f"people must be distinct, got {[p.value for p in people]}")
        self._world = world
        self._outcomes: dict[PersonId, Outcome | Undecided] = dict(outcomes)

    @classmethod
    def start(cls, world: WorldId, people: tuple[PersonId, ...]) -> PersonOutcomes:
        return cls(world, tuple((person, Undecided()) for person in people))

    @classmethod
    def from_memento(cls, memento: PersonOutcomesMemento, nouns: DeclaredNouns) -> PersonOutcomes:
        for entry in memento.outcomes:
            nouns.require_declared_character(entry.person)
        declared = {character.person_id for character in nouns.all_characters()}
        recorded = {entry.person for entry in memento.outcomes}
        if recorded != declared:
            missing = sorted(person.value for person in declared - recorded)
            raise MementoDoesNotMatchDesignException(f"world {memento.world_id.value} has no outcome for {missing}")
        return cls(
            memento.world_id,
            tuple(
                (entry.person, DeclaredOutcome(nouns.outcome_of(entry.outcome)))
                if isinstance(entry.outcome, OutcomeId)
                else (entry.person, entry.outcome)
                for entry in memento.outcomes
            ),
        )

    @property
    def world(self) -> WorldId:
        return self._world

    def memento(self) -> PersonOutcomesMemento:
        return PersonOutcomesMemento(
            world_id=self._world,
            outcomes=tuple(
                OutcomeOfPerson(person, outcome.outcome.outcome_id if isinstance(outcome, DeclaredOutcome) else outcome)
                for person, outcome in self._outcomes.items()
            ),
        )

    def decide(self, person: PersonId, outcome: Outcome, at: WorldTick) -> None:
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
                at=at,
            )
        )

    def outcome_of(self, person: PersonId) -> Outcome | Undecided:
        if person not in self._outcomes:
            raise PersonNotInWorldException(f"{person.value} is not in the world {self._world.value}")
        return self._outcomes[person]

    def has_left_the_world(self, person: PersonId) -> bool:
        # 作者の結末が決まった人は、体が世界から外れる。死んだ人は外れない。
        return isinstance(self.outcome_of(person), DeclaredOutcome)

    def all_decided(self) -> bool:
        return not self.undecided_people()

    def undecided_people(self) -> tuple[PersonId, ...]:
        return tuple(person for person, outcome in self._outcomes.items() if isinstance(outcome, Undecided))
