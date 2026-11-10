from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.condition.subject import Anyone
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, PersonId, WorldId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
    from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


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


@final
@dataclass(frozen=True)
class ActionLastDoneAt:
    who: PersonId | Anyone
    action: ActionKind | InteractionId
    at: WorldTick


@final
@dataclass(frozen=True)
class LatestActionsMemento:
    world_id: WorldId
    last_done: frozenset[ActionLastDoneAt]

    def __post_init__(self) -> None:
        keys = [(done.who, done.action) for done in self.last_done]
        if len(set(keys)) != len(keys):
            raise RepeatedMementoKeyException(f"world {self.world_id} has an action last done at two ticks")


class LatestActions(AggregateRoot[LatestActionsEvent]):
    def __init__(self, world_id: WorldId) -> None:
        super().__init__()
        self._world_id = world_id
        self._last_done: dict[tuple[PersonId | Anyone, ActionKind | InteractionId], WorldTick] = {}

    @classmethod
    def from_memento(cls, memento: LatestActionsMemento, design: WorldDesign) -> LatestActions:
        latest = cls(memento.world_id)
        latest._last_done = {(done.who, done.action): done.at for done in memento.last_done}
        return latest

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> LatestActionsMemento:
        return LatestActionsMemento(
            world_id=self._world_id,
            last_done=frozenset(ActionLastDoneAt(who, action, at) for (who, action), at in self._last_done.items()),
        )

    def note(self, attempt: ActionAttempt, now: WorldTick) -> None:
        for action in attempt.done_as():
            self._last_done[(attempt.actor, action)] = now
            self._last_done[(Anyone(), action)] = now
        self.add_event(PersonActedEvent(**new_event_stamp(), world_id=self._world_id, attempt=attempt, at=now))

    def note_failed_attempt(self, refusal: ActionRefusal, now: WorldTick) -> None:
        self.add_event(ActionAttemptFailedEvent(**new_event_stamp(), world_id=self._world_id, refusal=refusal, at=now))

    def last_done_at(self, who: PersonId | Anyone, action: ActionKind | InteractionId) -> WorldTick | NeverDone:
        return self._last_done.get((who, action), NeverDone())
