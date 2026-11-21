from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.perception.perception_cause import (
    ActionFailed,
    ActionTaken,
    HappeningFiring,
    JointActionSettling,
    PerceptionCause,
    ReactionFiring,
    TimePassed,
    UnnamedCause,
)
from ai_rpg_world.game_world.domain.world_progress.world_clock import WorldTickAdvancedEvent
from ai_rpg_world.game_world.domain.world_records.joint_action_progress import (
    JointActionCompletedEvent,
    JointActionTimedOutEvent,
)
from ai_rpg_world.game_world.domain.world_records.latest_actions import ActionAttemptFailedEvent, PersonActedEvent
from ai_rpg_world.game_world.domain.world_records.scenario_progress import HappeningFiredEvent, ReactionFiredEvent

_ACTION_EVENT_KINDS: Final = (PersonActedEvent, ActionAttemptFailedEvent)

# 効果のイベントを、それを起こした行為や発火と一緒に届けるため、記録のイベントでまとまりを閉じる (D2206)。
_CAUSES_CLOSING_AN_OCCURRENCE: Final[dict[type[DomainEvent], Callable[[Any], PerceptionCause]]] = {
    PersonActedEvent: lambda event: ActionTaken(actor=event.attempt.actor, kind=event.attempt.kind()),
    ActionAttemptFailedEvent: lambda event: ActionFailed(
        actor=event.refusal.attempt.actor, kind=event.refusal.attempt.kind()
    ),
    HappeningFiredEvent: lambda event: HappeningFiring(happening=event.happening_id),
    ReactionFiredEvent: lambda event: ReactionFiring(reaction=event.reaction_id),
    JointActionCompletedEvent: lambda event: JointActionSettling(joint_action=event.joint_id, completed=True),
    JointActionTimedOutEvent: lambda event: JointActionSettling(joint_action=event.joint_id, completed=False),
}


@final
@dataclass(frozen=True)
class Occurrence:
    cause: PerceptionCause
    events: tuple[DomainEvent, ...]

    def from_actions(self) -> tuple[DomainEvent, ...]:
        return tuple(event for event in self.events if isinstance(event, _ACTION_EVENT_KINDS))

    def from_states(self) -> tuple[DomainEvent, ...]:
        return tuple(event for event in self.events if not isinstance(event, _ACTION_EVENT_KINDS))


@final
class OccurrencesInCommit:
    @classmethod
    def split(cls, committed: Sequence[DomainEvent]) -> tuple[Occurrence, ...]:
        events = sorted(committed, key=lambda event: event.sequence)
        if any(isinstance(event, WorldTickAdvancedEvent) for event in events):
            # 時の経過では、到着も使い切りも 1 つずつ別に起きる。まとめると、同じ tick に着いた 2 人の片方しか届かない (D2206)。
            return tuple(Occurrence(cause=TimePassed(), events=(event,)) for event in events)
        occurrences: list[Occurrence] = []
        pending: list[DomainEvent] = []
        for event in events:
            pending.append(event)
            cause_of = _CAUSES_CLOSING_AN_OCCURRENCE.get(type(event))
            if cause_of is not None:
                occurrences.append(Occurrence(cause=cause_of(event), events=tuple(pending)))
                pending = []
        if not pending:
            return tuple(occurrences)
        if occurrences:
            last = occurrences.pop()
            return (*occurrences, Occurrence(cause=last.cause, events=(*last.events, *pending)))
        return (
            Occurrence(cause=UnnamedCause(tuple(type(event).__name__ for event in pending)), events=tuple(pending)),
        )
