from __future__ import annotations

from ai_rpg_world.eventing import AggregateRoot, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.spot import SpotAtmosphere, SpotDeclaration
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import UnknownSpotException
from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.game_world.domain.whereabouts.spot_atmosphere_events import SpotAtmosphereChangedEvent


class SpotAtmospheres(AggregateRoot[SpotAtmosphereChangedEvent]):
    def __init__(self, world_id: WorldId, spots: tuple[SpotDeclaration, ...]) -> None:
        super().__init__()
        self._world_id = world_id
        self._atmospheres = {declared.spot_id: declared.atmosphere for declared in spots}

    @property
    def world_id(self) -> WorldId:
        return self._world_id

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
