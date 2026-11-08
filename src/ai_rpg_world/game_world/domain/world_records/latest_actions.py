from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.condition.subject import Anyone
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, PersonId, WorldId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
    from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal


@final
@dataclass(frozen=True)
class NeverDone:
    def later_of(self, baseline: WorldTick) -> WorldTick:
        return baseline


@final
@dataclass(frozen=True, kw_only=True)
class PersonActedEvent(DomainEvent):
    world_id: WorldId
    attempt: ActionAttempt
    at: WorldTick


@final
@dataclass(frozen=True, kw_only=True)
class ActionAttemptFailedEvent(DomainEvent):
    world_id: WorldId
    refusal: ActionRefusal
    at: WorldTick


LatestActionsEvent = PersonActedEvent | ActionAttemptFailedEvent


class LatestActions(AggregateRoot[LatestActionsEvent]):
    def __init__(self, world_id: WorldId) -> None:
        super().__init__()
        self._world_id = world_id
        self._last_done: dict[tuple[PersonId | Anyone, ActionKind | InteractionId], WorldTick] = {}

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def note(self, attempt: ActionAttempt, now: WorldTick) -> None:
        for action in attempt.done_as():
            self._last_done[(attempt.actor, action)] = now
            self._last_done[(Anyone(), action)] = now
        self.add_event(PersonActedEvent(**new_event_stamp(), world_id=self._world_id, attempt=attempt, at=now))

    def note_failed_attempt(self, refusal: ActionRefusal, now: WorldTick) -> None:
        self.add_event(ActionAttemptFailedEvent(**new_event_stamp(), world_id=self._world_id, refusal=refusal, at=now))

    def last_done_at(self, who: PersonId | Anyone, action: ActionKind | InteractionId) -> WorldTick | NeverDone:
        return self._last_done.get((who, action), NeverDone())
