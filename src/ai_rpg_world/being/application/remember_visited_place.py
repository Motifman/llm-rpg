from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.visited_places import VisitedPlacesRepository


@dataclass(frozen=True, kw_only=True)
class RememberVisitedPlaceCommand:
    being_id: BeingId
    environment_name: str
    place: str


class RememberVisitedPlace:
    def __init__(self, *, visited_places: VisitedPlacesRepository) -> None:
        self._visited_places = visited_places

    def execute(self, command: RememberVisitedPlaceCommand) -> None:
        places = self._visited_places.get(command.being_id)
        places.visit(environment_name=command.environment_name, place=command.place)
        self._visited_places.save(places)


__all__ = ["RememberVisitedPlace", "RememberVisitedPlaceCommand"]
