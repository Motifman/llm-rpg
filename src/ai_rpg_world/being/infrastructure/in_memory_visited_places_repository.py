from __future__ import annotations

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.visited_places import VisitedPlaces, VisitedPlacesRepository


def _copy(places: VisitedPlaces) -> VisitedPlaces:
    return VisitedPlaces(places.being_id, places.places)


class InMemoryVisitedPlacesRepository(VisitedPlacesRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self) -> None:
        self._by_being: dict[BeingId, VisitedPlaces] = {}

    def get(self, being_id: BeingId) -> VisitedPlaces:
        stored = self._by_being.get(being_id)
        return VisitedPlaces.empty(being_id) if stored is None else _copy(stored)

    def save(self, places: VisitedPlaces) -> None:
        if not isinstance(places, VisitedPlaces):
            raise TypeError("places must be VisitedPlaces")
        self._by_being[places.being_id] = _copy(places)

    def replace_all_by_being(self, places: VisitedPlaces) -> None:
        self.save(places)
