from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Union, final

from typing_extensions import assert_never

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.game_world.domain.value_object.readiness_to_act import (
    FreeToAct,
    InTheMiddleOfAction,
    ReadinessToAct,
    UnableToAct,
)
from ai_rpg_world.play_session.domain.play_session_exception import (
    RoundAlreadyOpenException,
    RoundNotOpenException,
    RoundStillHasTurnsException,
    RoundValidationException,
    TurnNotDueException,
)


@final
@dataclass(frozen=True)
class RoundCount:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1:
            raise RoundValidationException(f"a round count must be a positive int, got {self.value!r}")


@final
@dataclass(frozen=True)
class Acted:
    pass


@final
@dataclass(frozen=True)
class Waited:
    pass


TurnOutcome = Union[Acted, Waited]


@final
@dataclass(frozen=True)
class RoundOpenedEvent(DomainEvent):
    world: WorldId
    round: int
    due: tuple[PersonId, ...]


@final
@dataclass(frozen=True)
class TurnFinishedEvent(DomainEvent):
    world: WorldId
    round: int
    person: PersonId
    order: int
    outcome: TurnOutcome


@final
@dataclass(frozen=True)
class RoundClosedEvent(DomainEvent):
    world: WorldId
    round: int


TurnRoundsEvent = Union[RoundOpenedEvent, TurnFinishedEvent, RoundClosedEvent]


class TurnRounds(AggregateRoot[TurnRoundsEvent]):
    def __init__(self, world: WorldId, *, round_limit: RoundCount, wake_waiting_after: RoundCount) -> None:
        super().__init__()
        self._world = world
        self._round_limit = round_limit
        self._wake_waiting_after = wake_waiting_after
        self._closed_rounds = 0
        self._due: tuple[PersonId, ...] | None = None
        self._finished: list[PersonId] = []
        self._waiting_since: dict[PersonId, int] = {}
        self._called: set[PersonId] = set()

    @property
    def world(self) -> WorldId:
        return self._world

    def open_round(self, readiness: Mapping[PersonId, ReadinessToAct]) -> None:
        if self._due is not None:
            raise RoundAlreadyOpenException(f"round {self._current_round} of {self._world.value} is already open")
        self._wake_those_waited_long_enough()
        self._due = tuple(person for person, ready in readiness.items() if self._takes_turn(person, ready))
        # 気を失っていたあいだの呼びかけで、気がついたあとの移動中にターンが回らないよう、持ち越さない
        self._called &= set(self._due)
        self._finished = []
        self.add_event(
            RoundOpenedEvent(**new_event_stamp(), world=self._world, round=self._current_round, due=self._due)
        )

    def due_turns(self) -> tuple[PersonId, ...]:
        due = self._open_due()
        return tuple(person for person in due if person not in self._finished)

    def hear_call(self, person: PersonId) -> None:
        self._waiting_since.pop(person, None)
        self._called.add(person)

    def finish_turn(self, person: PersonId, outcome: TurnOutcome) -> None:
        if person not in self.due_turns():
            raise TurnNotDueException(f"{person.value} has no turn left in round {self._current_round}")
        self._finished.append(person)
        # 自分の行為が呼んだ観測で、すぐまたターンが回らないよう、行為の確定のあとで呼びかけを消す
        self._called.discard(person)
        match outcome:
            case Waited():
                self._waiting_since[person] = self._current_round
            case Acted():
                pass
            case _:
                assert_never(outcome)
        self.add_event(
            TurnFinishedEvent(
                **new_event_stamp(),
                world=self._world,
                round=self._current_round,
                person=person,
                order=len(self._finished),
                outcome=outcome,
            )
        )

    def close_round(self) -> None:
        remaining = self.due_turns()
        if remaining:
            raise RoundStillHasTurnsException(
                f"round {self._current_round} still has turns for {[p.value for p in remaining]}"
            )
        closed = self._current_round
        self._closed_rounds += 1
        self._due = None
        self.add_event(RoundClosedEvent(**new_event_stamp(), world=self._world, round=closed))

    def has_reached_round_limit(self) -> bool:
        return self._closed_rounds >= self._round_limit.value

    @property
    def _current_round(self) -> int:
        return self._closed_rounds + 1

    def _open_due(self) -> tuple[PersonId, ...]:
        if self._due is None:
            raise RoundNotOpenException(f"no round of {self._world.value} is open")
        return self._due

    def _wake_those_waited_long_enough(self) -> None:
        for person, since in tuple(self._waiting_since.items()):
            if self._current_round - since > self._wake_waiting_after.value:
                del self._waiting_since[person]

    def _takes_turn(self, person: PersonId, readiness: ReadinessToAct) -> bool:
        match readiness:
            case FreeToAct():
                return person not in self._waiting_since
            case InTheMiddleOfAction():
                # 行っているあいだは話すことしかできないので、呼びかけられたときだけ回す
                return person in self._called
            case UnableToAct():
                return False
            case _:
                assert_never(readiness)
