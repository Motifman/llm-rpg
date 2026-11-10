from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, SpotDeclaration
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    PassageAlreadyRemovedException,
    UnknownPassageException,
)
from ai_rpg_world.game_world.domain.value_object import PassageId, PassageStateName, WorldId
from ai_rpg_world.game_world.domain.whereabouts.passage_in_state import PassageInState
from ai_rpg_world.game_world.domain.whereabouts.passage_state_events import (
    PassageRemovedEvent,
    PassageRevealedEvent,
    PassageStateChangedEvent,
    PassageStatesEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


class PassagePresence(Enum):
    HIDDEN = "HIDDEN"
    PRESENT = "PRESENT"
    REMOVED = "REMOVED"


@final
@dataclass(frozen=True)
class PassageCondition:
    passage: PassageId
    state: PassageStateName
    presence: PassagePresence


@final
@dataclass(frozen=True)
class PassageStatesMemento:
    world_id: WorldId
    passages: frozenset[PassageCondition]

    def __post_init__(self) -> None:
        passages = [condition.passage for condition in self.passages]
        if len(set(passages)) != len(passages):
            raise RepeatedMementoKeyException(f"world {self.world_id} has a passage in two conditions")


class PassageStates(AggregateRoot[PassageStatesEvent]):
    def __init__(self, world_id: WorldId, passages: tuple[PassageDeclaration, ...]) -> None:
        super().__init__()
        self._world_id = world_id
        self._declared = {passage.passage_id: passage for passage in passages}
        self._states = {passage.passage_id: passage.initial_state for passage in passages}
        self._presence = {
            passage.passage_id: PassagePresence.HIDDEN if passage.hidden_until_revealed else PassagePresence.PRESENT
            for passage in passages
        }

    @classmethod
    def from_memento(cls, memento: PassageStatesMemento, design: WorldDesign) -> PassageStates:
        remembered: dict[PassageId, PassageCondition] = {}
        for condition in memento.passages:
            passage = design.nouns.passage_of(condition.passage)
            passage.state(condition.state)
            remembered[passage.passage_id] = condition
        declared = design.nouns.all_passages()
        if remembered.keys() != {passage.passage_id for passage in declared}:
            raise MementoDoesNotMatchDesignException(
                f"PassageStates of {memento.world_id.value} does not have every declared passage"
            )
        states = cls(memento.world_id, declared)
        states._states = {passage: condition.state for passage, condition in remembered.items()}
        states._presence = {passage: condition.presence for passage, condition in remembered.items()}
        return states

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> PassageStatesMemento:
        return PassageStatesMemento(
            world_id=self._world_id,
            passages=frozenset(
                PassageCondition(passage, state, self._presence[passage]) for passage, state in self._states.items()
            ),
        )

    def change_state(self, passage: PassageDeclaration, new_state: PassageStateName) -> None:
        self._require_not_removed(passage)
        passage.state(new_state)
        before = self._states[passage.passage_id]
        if before == new_state:
            return
        self._states[passage.passage_id] = new_state
        self.add_event(
            PassageStateChangedEvent(
                **new_event_stamp(),
                world_id=self._world_id,
                passage=passage.passage_id,
                before=before,
                after=new_state,
            )
        )

    def reveal(self, passage: PassageDeclaration) -> None:
        self._require_not_removed(passage)
        if self._presence[passage.passage_id] is PassagePresence.PRESENT:
            return
        self._presence[passage.passage_id] = PassagePresence.PRESENT
        self.add_event(PassageRevealedEvent(**new_event_stamp(), world_id=self._world_id, passage=passage.passage_id))

    def remove(self, passage: PassageDeclaration) -> None:
        if self._presence_of(passage) is PassagePresence.REMOVED:
            return
        self._presence[passage.passage_id] = PassagePresence.REMOVED
        self.add_event(PassageRemovedEvent(**new_event_stamp(), world_id=self._world_id, passage=passage.passage_id))

    def is_traversable(self, passage: PassageDeclaration) -> bool:
        self._presence_of(passage)
        return self._is_traversable(passage.passage_id)

    def closed_passages(self) -> frozenset[PassageId]:
        return frozenset(passage_id for passage_id in self._declared if not self._is_traversable(passage_id))

    def passages_from(self, spot: SpotDeclaration, declared: tuple[PassageDeclaration, ...]) -> tuple[PassageId, ...]:
        return tuple(
            passage.passage_id
            for passage in declared
            if self._presence_of(passage) is PassagePresence.PRESENT and _leaves(passage, spot)
        )

    def in_state(self, passage: PassageDeclaration) -> PassageInState:
        self._presence_of(passage)
        return PassageInState(passage=passage, state=self._states[passage.passage_id])

    def _is_traversable(self, passage_id: PassageId) -> bool:
        return self._presence[passage_id] is PassagePresence.PRESENT and self._declared[passage_id].allows(
            self._states[passage_id]
        )

    def _presence_of(self, passage: PassageDeclaration) -> PassagePresence:
        if passage.passage_id not in self._presence:
            raise UnknownPassageException(f"PassageStates of {self._world_id.value} has no {passage.passage_id.value}")
        return self._presence[passage.passage_id]

    def _require_not_removed(self, passage: PassageDeclaration) -> None:
        if self._presence_of(passage) is PassagePresence.REMOVED:
            raise PassageAlreadyRemovedException(f"{passage.passage_id.value} has already been removed")


def _leaves(passage: PassageDeclaration, spot: SpotDeclaration) -> bool:
    near, far = passage.ends
    return spot.spot_id == near or (passage.two_way and spot.spot_id == far)
