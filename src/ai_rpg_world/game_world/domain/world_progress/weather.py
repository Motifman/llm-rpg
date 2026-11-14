from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.time_and_weather import WeatherDeclaration, WeatherState
from ai_rpg_world.game_world.domain.value_object import WorldId


@final
@dataclass(frozen=True)
class WeatherChangedEvent(DomainEvent):
    world_id: WorldId
    before: WeatherState
    after: WeatherState


@final
@dataclass(frozen=True)
class WeatherMemento:
    world_id: WorldId
    current: WeatherState


class Weather(AggregateRoot[WeatherChangedEvent]):
    def __init__(self, world_id: WorldId, current: WeatherState) -> None:
        super().__init__()
        self._world_id = world_id
        self._current = current

    @classmethod
    def from_declaration(cls, world_id: WorldId, declaration: WeatherDeclaration) -> Weather:
        return cls(world_id, WeatherState(declaration.initial))

    @classmethod
    def from_memento(cls, memento: WeatherMemento) -> Weather:
        return cls(memento.world_id, memento.current)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> WeatherMemento:
        return WeatherMemento(world_id=self._world_id, current=self._current)

    def change(self, new_state: WeatherState) -> None:
        if new_state == self._current:
            return
        before = self._current
        self._current = new_state
        self.add_event(
            WeatherChangedEvent(**new_event_stamp(), world_id=self._world_id, before=before, after=new_state)
        )

    def current(self) -> WeatherState:
        return self._current
