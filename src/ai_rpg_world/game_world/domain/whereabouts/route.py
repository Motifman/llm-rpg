from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import BrokenRouteException, EmptyRouteException
from ai_rpg_world.game_world.domain.value_object import SpotId


@final
@dataclass(frozen=True)
class Route:
    start: SpotId
    legs: tuple[PassageDeclaration, ...]

    def __post_init__(self) -> None:
        if not self.legs:
            raise EmptyRouteException(f"Route from {self.start.value!r} has no legs")
        self._stops()

    @property
    def destination(self) -> SpotId:
        return self._stops()[-1]

    def end_of_leg(self, leg_index: int) -> SpotId:
        return self._stops()[leg_index + 1]

    def _stops(self) -> tuple[SpotId, ...]:
        stops = [self.start]
        for leg in self.legs:
            here = stops[-1]
            near, far = leg.ends
            if here == near:
                stops.append(far)
            elif here == far and leg.two_way:
                stops.append(near)
            else:
                raise BrokenRouteException(
                    f"Route from {self.start.value!r} cannot walk {leg.passage_id.value} from {here.value!r}"
                )
        return tuple(stops)
