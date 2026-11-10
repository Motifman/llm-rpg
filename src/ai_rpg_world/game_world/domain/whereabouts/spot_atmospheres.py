from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.spot import SpotAtmosphere, SpotDeclaration
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import UnknownSpotException
from ai_rpg_world.game_world.domain.value_object import SpotId, WorldId
from ai_rpg_world.game_world.domain.whereabouts.spot_atmosphere_events import SpotAtmosphereChangedEvent

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class AtmosphereAtSpot:
    spot: SpotId
    atmosphere: SpotAtmosphere


@final
@dataclass(frozen=True)
class SpotAtmospheresMemento:
    world_id: WorldId
    atmospheres: frozenset[AtmosphereAtSpot]

    def __post_init__(self) -> None:
        spots = [entry.spot for entry in self.atmospheres]
        if len(set(spots)) != len(spots):
            raise RepeatedMementoKeyException(f"world {self.world_id} has a spot with two atmospheres")


class SpotAtmospheres(AggregateRoot[SpotAtmosphereChangedEvent]):
    def __init__(self, world_id: WorldId, atmospheres: Mapping[SpotId, SpotAtmosphere]) -> None:
        super().__init__()
        self._world_id = world_id
        self._atmospheres = dict(atmospheres)

    @classmethod
    def start(cls, world_id: WorldId, spots: tuple[SpotDeclaration, ...]) -> SpotAtmospheres:
        return cls(world_id, {declared.spot_id: declared.atmosphere for declared in spots})

    @classmethod
    def from_memento(cls, memento: SpotAtmospheresMemento, design: WorldDesign) -> SpotAtmospheres:
        remembered = {design.nouns.spot_of(entry.spot).spot_id: entry.atmosphere for entry in memento.atmospheres}
        declared = design.nouns.all_spots()
        if remembered.keys() != {spot.spot_id for spot in declared}:
            raise MementoDoesNotMatchDesignException(
                f"SpotAtmospheres of {memento.world_id.value} does not have every declared spot"
            )
        return cls(memento.world_id, remembered)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> SpotAtmospheresMemento:
        return SpotAtmospheresMemento(
            world_id=self._world_id,
            atmospheres=frozenset(AtmosphereAtSpot(spot, atmosphere) for spot, atmosphere in self._atmospheres.items()),
        )

    def change(self, spot: SpotDeclaration, atmosphere: SpotAtmosphere) -> None:
        before = self.atmosphere_of(spot)
        if before == atmosphere:
            return
        self._atmospheres[spot.spot_id] = atmosphere
        self.add_event(
            SpotAtmosphereChangedEvent(
                **new_event_stamp(),
                world_id=self._world_id,
                spot=spot.spot_id,
                before=before,
                after=atmosphere,
            )
        )

    def atmosphere_of(self, spot: SpotDeclaration) -> SpotAtmosphere:
        if spot.spot_id not in self._atmospheres:
            raise UnknownSpotException(f"SpotAtmospheres of {self._world_id.value} has no {spot.spot_id.value}")
        return self._atmospheres[spot.spot_id]
