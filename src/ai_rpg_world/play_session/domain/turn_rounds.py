from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
from ai_rpg_world.play_session.domain.addressed_people import AddressedPeople
from ai_rpg_world.play_session.domain.choice_failure_streak import ChoiceFailureStreak
from ai_rpg_world.play_session.domain.failures_by_person import FailuresByPerson
from ai_rpg_world.play_session.domain.observations_held_while_choosing import ObservationsHeldWhileChoosing
from ai_rpg_world.play_session.domain.open_round import OpenRound
from ai_rpg_world.play_session.domain.play_session_exception import (
    RoundAlreadyOpenException,
    RoundNotOpenException,
    RoundStillHasTurnsException,
    RoundValidationException,
)
from ai_rpg_world.play_session.domain.turn_skip import SkippedTurn, TurnSkipReason
from ai_rpg_world.play_session.domain.waiting_people import WaitingPeople


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


@final
@dataclass(frozen=True)
class ChoseNoAction:
    pass


TurnOutcome = Union[Acted, Waited, ChoiceFailed, ChoseNoAction]


@final
@dataclass(frozen=True)
class RoundLimitReached:
    pass


@final
@dataclass(frozen=True)
class ChoosingKeptFailing:
    reasons: tuple[str, ...]


ReasonToStop = Union[RoundLimitReached, ChoosingKeptFailing]


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
        self._open: OpenRound | None = None
        self._held = ObservationsHeldWhileChoosing()
        self._waiting = WaitingPeople()
        self._addressed = AddressedPeople()
        self._failures_by_person = FailuresByPerson()
        self._failure_streak = ChoiceFailureStreak()

    @property
    def world(self) -> WorldId:
        return self._world

    def open_round(self, readiness: Mapping[PersonId, ReadinessToAct]) -> None:
        if self._open is not None:
            raise RoundAlreadyOpenException(f"round {self._current_round} of {self._world.value} is already open")
        self._waiting = self._waiting.woken_after(self._current_round, self._wake_waiting_after.value)
        skips = {person: self._skip_reason(person, ready) for person, ready in readiness.items()}
        due = tuple(person for person, reason in skips.items() if reason is None)
        self._open = OpenRound(self._current_round, due)
        # 巡りを閉じられるのは全員がターンを終えて預かりを回し切ったあとなので、ここで捨てるものは無い
        self._held = ObservationsHeldWhileChoosing()
        # 気を失っていたあいだに向けられたもので、気がついたあとの移動中にターンが回らないよう、持ち越さない
        self._addressed = self._addressed.only(due)
        self.add_event(
            RoundOpenedEvent(
                **new_event_stamp(),
                world=self._world,
                round=self._current_round,
                due=due,
                skipped=tuple(SkippedTurn(person, reason) for person, reason in skips.items() if reason is not None),
            )
        )

    def due_turns(self) -> tuple[PersonId, ...]:
        return self._opened().remaining()

    def begin_choosing(self, people: Sequence[PersonId]) -> None:
        opened = self._opened()
        for person in people:
            opened.check_turn_left(person)
        self._held = self._held.began(people)

    def finish_choosing(self, person: PersonId) -> None:
        self._held = self._held.finished_choosing(person)

    def notice_observation(self, person: PersonId, observation: Observation) -> None:
        # 選んでいるあいだに書き込むと、選び終えて書く試みと競り合う。本人は見ずに選んだので、ターンを終えてから渡す
        if self._held.is_choosing(person):
            self._held = self._held.hold(person, observation)
            return
        self._pass_on(person, observation)

    def finish_turn(self, person: PersonId, outcome: TurnOutcome) -> None:
        self._open = self._opened().finished_by(person)
        self._held = self._held.finished_choosing(person)
        # 自分の行為に返ってきた観測で、すぐまたターンが回らないよう、行為の確定のあとで消す
        self._addressed = self._addressed.without(person)
        match outcome:
            case Waited():
                self._waiting = self._waiting.started(person, self._current_round, TurnSkipReason.WAITING)
                self._count_choice_made(person)
            case Acted() | ChoseNoAction():
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
                order=self._open.last_order,
                outcome=outcome,
            )
        )
        # 消したあとで数えるので、選んでいるあいだに届いた呼びかけは次の巡りに残る
        held = self._held.held_for(person)
        self._held = self._held.released(person)
        for observation in held:
            self._pass_on(person, observation)

    def close_round(self) -> None:
        remaining = self.due_turns()
        if remaining:
            raise RoundStillHasTurnsException(
                f"round {self._current_round} still has turns for {[p.value for p in remaining]}"
            )
        closed = self._current_round
        self._closed_rounds += 1
        self._open = None
        self.add_event(RoundClosedEvent(**new_event_stamp(), world=self._world, round=closed))

    def reason_to_stop(self) -> ReasonToStop | None:
        # 上限は正常な終わりなので、重なったときに上限で覆うと、壊れた run が正常に終わったように記録される
        if self._failure_streak.given_up_on:
            return ChoosingKeptFailing(self._failure_streak.given_up_on)
        if self._closed_rounds >= self._round_limit.value:
            return RoundLimitReached()
        return None

    @property
    def _current_round(self) -> int:
        return self._closed_rounds + 1

    def _opened(self) -> OpenRound:
        if self._open is None:
            raise RoundNotOpenException(f"no round of {self._world.value} is open")
        return self._open

    def _pass_on(self, person: PersonId, observation: Observation) -> None:
        if observation.wants_wake is True:
            self._waiting = self._waiting.woken(person)
        if observation.addressed_to_self is True:
            self._addressed = self._addressed.with_person(person)
        self.add_event(
            ObservationPassedOnEvent(**new_event_stamp(), world=self._world, person=person, observation=observation)
        )

    def _count_choice_made(self, person: PersonId) -> None:
        self._failures_by_person = self._failures_by_person.cleared(person)
        self._failure_streak = self._failure_streak.broken()

    def _count_choice_failed(self, person: PersonId, reason: str) -> None:
        self._failures_by_person = self._failures_by_person.failed(person)
        if self._failures_by_person.has_failed_enough_to_wait(person):
            self._waiting = self._waiting.started(
                person, self._current_round, TurnSkipReason.WAITING_AFTER_CHOICES_KEPT_FAILING
            )
            self._failures_by_person = self._failures_by_person.cleared(person)
        self._failure_streak = self._failure_streak.failed(reason, self._current_round)

    def _skip_reason(self, person: PersonId, readiness: ReadinessToAct) -> TurnSkipReason | None:
        match readiness:
            case FreeToAct():
                return self._waiting.reason_of(person)
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
