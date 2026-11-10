from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.exception.world_progress_exception import WorldAlreadyEndedException
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class WorldEndedEvent(DomainEvent):
    world_id: WorldId
    at: WorldTick


@final
@dataclass(frozen=True)
class WorldEndingMemento:
    world_id: WorldId
    ended: bool


class WorldEnding(AggregateRoot[WorldEndedEvent]):
    def __init__(self, world_id: WorldId, ended: bool) -> None:
        super().__init__()
        self._world_id = world_id
        self._ended = ended

    @classmethod
    def start(cls, world_id: WorldId) -> WorldEnding:
        return cls(world_id, False)

    @classmethod
    def from_memento(cls, memento: WorldEndingMemento, design: WorldDesign) -> WorldEnding:
        return cls(memento.world_id, memento.ended)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> WorldEndingMemento:
        return WorldEndingMemento(world_id=self._world_id, ended=self._ended)

    def end(self, now: WorldTick) -> None:
        if self._ended:
            raise WorldAlreadyEndedException(f"world {self._world_id} has already ended")
        self._ended = True
        self.add_event(WorldEndedEvent(**new_event_stamp(), world_id=self._world_id, at=now))

    def has_ended(self) -> bool:
        return self._ended
