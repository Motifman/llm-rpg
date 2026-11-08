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
    passages: tuple[PassageDeclaration, ...]

    def __post_init__(self) -> None:
        if not self.passages:
            raise EmptyRouteException(f"Route from {self.start.value!r} has no passages")
        self._stops()

    @property
    def destination(self) -> SpotId:
        return self._stops()[-1]

    def end_of_passage(self, passage_index: int) -> SpotId:
        return self._stops()[passage_index + 1]

    def _stops(self) -> tuple[SpotId, ...]:
        stops = [self.start]
        for passage in self.passages:
            here = stops[-1]
            near, far = passage.ends
            if here == near:
                stops.append(far)
            elif here == far and passage.two_way:
                stops.append(near)
            else:
                raise BrokenRouteException(
                    f"Route from {self.start.value!r} cannot walk {passage.passage_id.value} from {here.value!r}"
                )
        return tuple(stops)
