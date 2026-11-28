from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from typing import Any, Protocol, final

from typing_extensions import assert_never

from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.contract import UNKNOWN, Observation
from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import PerceptionDeliveryReport
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.application.play_rounds import DiscardedChoice
from ai_rpg_world.play_session.domain.turn_rounds import (
    Acted,
    ChoiceFailed,
    ObservationPassedOnEvent,
    RoundClosedEvent,
    RoundOpenedEvent,
    TurnFinishedEvent,
    TurnOutcome,
    TurnRoundsEvent,
    Waited,
)


class GameWorldTraceKind:
    # 古い世界の kind と混ざらないよう、新しい世界の kind には接頭辞を付ける
    ROUND_OPENED = "game_world.round_opened"
    TURN_FINISHED = "game_world.turn_finished"
    ROUND_CLOSED = "game_world.round_closed"
    OBSERVATION_PASSED_ON = "game_world.observation_passed_on"
    CHOICE_DISCARDED = "game_world.choice_discarded"
    PERCEPTION_DELIVERED = "game_world.perception_delivered"
    WORLD_EVENT = "game_world.world_event"
    CHOICE = "game_world.choice"
    ACTION_RESULT = "game_world.action_result"


class TraceLog(Protocol):
    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None: ...


@final
class NoTrace:
    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        pass


@final
class GameWorldTrace:
    def __init__(self, log: TraceLog, *, names: Mapping[PersonId, str], now: Callable[[], int]) -> None:
        self._log = log
        self._names = dict(names)
        self._now = now

    def record_turn_rounds_events(self, events: Sequence[TurnRoundsEvent]) -> None:
        for event in events:
            self._record_turn_rounds_event(event)

    def record_discarded(self, discarded: Sequence[DiscardedChoice]) -> None:
        for choice in discarded:
            call = None if choice.exchange is None else choice.exchange.replies[-1].tool_call
            self._log.record(
                GameWorldTraceKind.CHOICE_DISCARDED,
                tick=self._now(),
                person=self._person(choice.person),
                started_thinking=choice.exchange is not None or choice.failure is not None,
                failure=choice.failure,
                tool=None if call is None else call.tool_name,
                arguments=None if call is None else dict(call.arguments),
            )

    def record_being_turn(self, kind: str, person: PersonId, **payload: Any) -> None:
        self._log.record(kind, tick=self._now(), person=self._person(person), **payload)

    def name_of(self, person: PersonId) -> str:
        return self._names.get(person, person.value)

    def jsonable(self, value: object) -> Any:
        return self._jsonable(value)

    def record_perception_report(self, report: PerceptionDeliveryReport) -> None:
        self._log.record(
            GameWorldTraceKind.PERCEPTION_DELIVERED,
            tick=report.at.value,
            cause={"type": type(report.cause).__name__, **self._jsonable_fields(report.cause)},
            stimuli=[
                {
                    "sense": self._jsonable(result.stimulus.sense),
                    "text": result.stimulus.text,
                    "where": self._jsonable(result.stimulus.where),
                    "addressed_to": [self._person(p) for p in sorted(result.stimulus.addressed_to, key=_id)],
                    "perceived_by": [self._person(p) for p in result.perceived_by],
                    "kept_for": [self._person(p) for p in result.kept_for],
                    "missed_by": [
                        {**self._person(p), "reason": reason.value} for p, reason in result.missed_by.items()
                    ],
                }
                for result in report.stimuli
            ],
        )

    def record_world_events(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            self._log.record(
                GameWorldTraceKind.WORLD_EVENT,
                tick=self._now(),
                event_type=type(event).__name__,
                **{k: v for k, v in self._jsonable_fields(event).items() if k not in _EVENT_STAMP},
            )

    def _jsonable_fields(self, value: object) -> dict[str, Any]:
        if not dataclasses.is_dataclass(value) or isinstance(value, type):
            return {}
        return {f.name: self._jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}

    def _jsonable(self, value: object) -> Any:
        if isinstance(value, PersonId):
            return self._person(value)
        if isinstance(value, Enum):
            # 数を値にした列挙は、数では読めないので名前で書く
            return value.value if isinstance(value.value, str) else value.name.lower()
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {str(self._jsonable(k)): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, (frozenset, set)):
            return sorted((self._jsonable(v) for v in value), key=str)
        if isinstance(value, (tuple, list)):
            return [self._jsonable(v) for v in value]
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            fields = self._jsonable_fields(value)
            # 識別子や名前のような値が 1 つだけの値オブジェクトは、中の値だけを書く
            if len(fields) == 1:
                return next(iter(fields.values()))
            return {"type": type(value).__name__, **fields}
        return repr(value)

    def _record_turn_rounds_event(self, event: TurnRoundsEvent) -> None:
        match event:
            case RoundOpenedEvent():
                self._log.record(
                    GameWorldTraceKind.ROUND_OPENED,
                    tick=self._now(),
                    round=event.round,
                    due=[self._person(person) for person in event.due],
                    skipped=[{**self._person(s.person), "reason": s.reason.value} for s in event.skipped],
                )
            case TurnFinishedEvent():
                self._log.record(
                    GameWorldTraceKind.TURN_FINISHED,
                    tick=self._now(),
                    round=event.round,
                    person=self._person(event.person),
                    order=event.order,
                    **_outcome(event.outcome),
                )
            case RoundClosedEvent():
                self._log.record(GameWorldTraceKind.ROUND_CLOSED, tick=self._now(), round=event.round)
            case ObservationPassedOnEvent():
                self._log.record(
                    GameWorldTraceKind.OBSERVATION_PASSED_ON,
                    tick=self._now(),
                    person=self._person(event.person),
                    **_observation(event.observation),
                )
            case _:
                assert_never(event)

    def _person(self, person: PersonId) -> dict[str, str]:
        return {"person_id": person.value, "name": self._names.get(person, person.value)}


_EVENT_STAMP = frozenset({"event_id", "occurred_at", "sequence"})


def _id(person: PersonId) -> str:
    return person.value


def _outcome(outcome: TurnOutcome) -> dict[str, Any]:
    match outcome:
        case Acted():
            return {"outcome": "acted", "reason": None}
        case Waited():
            return {"outcome": "waited", "reason": None}
        case ChoiceFailed():
            return {"outcome": "choice_failed", "reason": outcome.reason}
        case _:
            assert_never(outcome)


def _observation(observation: Observation) -> dict[str, Any]:
    named = observation.with_people_named(text_naming_people)
    return {
        "body": named.body,
        "route": type(observation.route).__name__,
        "subject_is_self": observation.subject_is_self,
        "wants_wake": observation.wants_wake,
        "addressed_to_self": "unknown" if observation.addressed_to_self is UNKNOWN else observation.addressed_to_self,
        "time": observation.time.display,
    }
