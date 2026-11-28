from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Union, final

from typing_extensions import assert_never

from ai_rpg_world.being.contract import Observation
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


@final
@dataclass(frozen=True)
class ChoiceFailed:
    reason: str


TurnOutcome = Union[Acted, Waited, ChoiceFailed]

# 同じ人がこの回数続けて選べなかったら、待つ人と同じ扱いにする (D1595、D2232 の 7 節)
_FAILURES_BEFORE_WAITING = 3
# 人を問わず失敗がこの件数続き、この巡りの数にまたがったら止める。健全な run の最長連続は 4、壊れた run の最短は 35 だった
# (design_decisions 214、D2232 の 7 節)
_FAILURES_TO_GIVE_UP = 8
_ROUNDS_TO_GIVE_UP = 2


class TurnSkipReason(Enum):
    WAITING = "waiting"
    IN_THE_MIDDLE_OF_ACTION_AND_NOT_ADDRESSED = "in_the_middle_of_action_and_not_addressed"
    UNABLE_TO_ACT = "unable_to_act"


@final
@dataclass(frozen=True)
class SkippedTurn:
    person: PersonId
    reason: TurnSkipReason


@final
@dataclass(frozen=True)
class RoundOpenedEvent(DomainEvent):
    world: WorldId
    round: int
    due: tuple[PersonId, ...]
    skipped: tuple[SkippedTurn, ...]


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


@final
@dataclass(frozen=True)
class ObservationPassedOnEvent(DomainEvent):
    world: WorldId
    person: PersonId
    observation: Observation


TurnRoundsEvent = Union[RoundOpenedEvent, TurnFinishedEvent, RoundClosedEvent, ObservationPassedOnEvent]


class TurnRounds(AggregateRoot[TurnRoundsEvent]):
    def __init__(self, world: WorldId, *, round_limit: RoundCount, wake_waiting_after: RoundCount) -> None:
        super().__init__()
        self._world = world
        self._round_limit = round_limit
        self._wake_waiting_after = wake_waiting_after
        self._closed_rounds = 0
        self._due: tuple[PersonId, ...] | None = None
        self._finished: list[PersonId] = []
        self._choosing: set[PersonId] = set()
        self._held_for: dict[PersonId, list[Observation]] = {}
        self._waiting_since: dict[PersonId, int] = {}
        self._addressed: set[PersonId] = set()
        self._failures_by_person: dict[PersonId, int] = {}
        self._failures_in_a_row: list[str] = []
        self._rounds_of_failures: set[int] = set()
        self._gave_up_on: tuple[str, ...] = ()

    @property
    def world(self) -> WorldId:
        return self._world

    def open_round(self, readiness: Mapping[PersonId, ReadinessToAct]) -> None:
        if self._due is not None:
            raise RoundAlreadyOpenException(f"round {self._current_round} of {self._world.value} is already open")
        self._wake_those_waited_long_enough()
        skips = {person: self._skip_reason(person, ready) for person, ready in readiness.items()}
        self._due = tuple(person for person, reason in skips.items() if reason is None)
        # 気を失っていたあいだに向けられたもので、気がついたあとの移動中にターンが回らないよう、持ち越さない
        self._addressed &= set(self._due)
        self._finished = []
        self._choosing = set()
        self.add_event(
            RoundOpenedEvent(
                **new_event_stamp(),
                world=self._world,
                round=self._current_round,
                due=self._due,
                skipped=tuple(SkippedTurn(person, reason) for person, reason in skips.items() if reason is not None),
            )
        )

    def due_turns(self) -> tuple[PersonId, ...]:
        due = self._open_due()
        return tuple(person for person in due if person not in self._finished)

    def begin_choosing(self, people: Sequence[PersonId]) -> None:
        due = self.due_turns()
        for person in people:
            if person not in due:
                raise TurnNotDueException(f"{person.value} has no turn left in round {self._current_round}")
        self._choosing.update(people)

    def finish_choosing(self, person: PersonId) -> None:
        self._choosing.discard(person)

    def notice_observation(self, person: PersonId, observation: Observation) -> None:
        # 選んでいるあいだに書き込むと、選び終えて書く試みと競り合う。本人は見ずに選んだので、ターンを終えてから渡す
        if person in self._choosing:
            self._held_for.setdefault(person, []).append(observation)
            return
        self._pass_on(person, observation)

    def finish_turn(self, person: PersonId, outcome: TurnOutcome) -> None:
        if person not in self.due_turns():
            raise TurnNotDueException(f"{person.value} has no turn left in round {self._current_round}")
        self._finished.append(person)
        self._choosing.discard(person)
        # 自分の行為に返ってきた観測で、すぐまたターンが回らないよう、行為の確定のあとで消す
        self._addressed.discard(person)
        match outcome:
            case Waited():
                self._waiting_since[person] = self._current_round
                self._count_choice_made(person)
            case Acted():
                self._count_choice_made(person)
            case ChoiceFailed():
                self._count_choice_failed(person, outcome.reason)
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
        # 消したあとで数えるので、選んでいるあいだに届いた呼びかけは次の巡りに残る
        for held in self._held_for.pop(person, []):
            self._pass_on(person, held)

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

    def has_given_up_choosing(self) -> bool:
        return bool(self._gave_up_on)

    def failures_given_up_on(self) -> tuple[str, ...]:
        return self._gave_up_on

    def has_reached_round_limit(self) -> bool:
        return self._closed_rounds >= self._round_limit.value

    @property
    def _current_round(self) -> int:
        return self._closed_rounds + 1

    def _open_due(self) -> tuple[PersonId, ...]:
        if self._due is None:
            raise RoundNotOpenException(f"no round of {self._world.value} is open")
        return self._due

    def _pass_on(self, person: PersonId, observation: Observation) -> None:
        if observation.wants_wake is True:
            self._waiting_since.pop(person, None)
        if observation.addressed_to_self is True:
            self._addressed.add(person)
        self.add_event(
            ObservationPassedOnEvent(**new_event_stamp(), world=self._world, person=person, observation=observation)
        )

    def _count_choice_made(self, person: PersonId) -> None:
        self._failures_by_person.pop(person, None)
        self._failures_in_a_row.clear()
        self._rounds_of_failures.clear()

    def _count_choice_failed(self, person: PersonId, reason: str) -> None:
        failures = self._failures_by_person.get(person, 0) + 1
        if failures >= _FAILURES_BEFORE_WAITING:
            self._waiting_since[person] = self._current_round
            failures = 0
        self._failures_by_person[person] = failures
        self._failures_in_a_row.append(reason)
        self._rounds_of_failures.add(self._current_round)
        # 一度止めると決めたら、後から選べたターンが届いても止めたままにし、止めたときの理由を残す
        if self._gave_up_on:
            return
        if len(self._failures_in_a_row) >= _FAILURES_TO_GIVE_UP and len(self._rounds_of_failures) >= _ROUNDS_TO_GIVE_UP:
            self._gave_up_on = tuple(self._failures_in_a_row)

    def _wake_those_waited_long_enough(self) -> None:
        for person, since in tuple(self._waiting_since.items()):
            if self._current_round - since > self._wake_waiting_after.value:
                del self._waiting_since[person]

    def _skip_reason(self, person: PersonId, readiness: ReadinessToAct) -> TurnSkipReason | None:
        match readiness:
            case FreeToAct():
                return TurnSkipReason.WAITING if person in self._waiting_since else None
            case InTheMiddleOfAction():
                # 行っているあいだは話すことしかできないので、自分に向けたものがあったときだけ回す。
                # 目立つ出来事で回すと、話す気の無い人に頼んで、断られる行動を選ばせる
                if person in self._addressed:
                    return None
                return TurnSkipReason.IN_THE_MIDDLE_OF_ACTION_AND_NOT_ADDRESSED
            case UnableToAct():
                return TurnSkipReason.UNABLE_TO_ACT
            case _:
                assert_never(readiness)


class TurnRoundsRepository(Protocol):
    def get(self, world: WorldId) -> TurnRounds: ...

    def save(self, rounds: TurnRounds) -> None: ...
