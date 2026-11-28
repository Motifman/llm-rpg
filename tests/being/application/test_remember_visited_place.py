from __future__ import annotations

from ai_rpg_world.being.application.remember_visited_place import RememberVisitedPlace, RememberVisitedPlaceCommand
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.visited_places import VisitedPlace
from ai_rpg_world.being.infrastructure.in_memory_visited_places_repository import InMemoryVisitedPlacesRepository

GEN = BeingId("being-gen")


def _remember(repository: InMemoryVisitedPlacesRepository, place: str) -> None:
    RememberVisitedPlace(visited_places=repository).execute(
        RememberVisitedPlaceCommand(being_id=GEN, environment_name="廃坑の山村", place=place)
    )


class TestRememberVisitedPlace:
    """RememberVisitedPlace が、いる場所を環境の名前と組にして、訪れた場所の記録に保存することを保証する。"""

    def test_place_is_saved_with_the_environment_name(self) -> None:
        """井戸にいると、廃坑の山村の井戸を訪れたと保存する。"""
        repository = InMemoryVisitedPlacesRepository()

        _remember(repository, "井戸")

        assert repository.get(GEN).places == (VisitedPlace(environment_name="廃坑の山村", place="井戸"),)

    def test_same_place_twice_is_kept_once(self) -> None:
        """同じ場所に 2 回いても、記録は 1 件のまま。"""
        repository = InMemoryVisitedPlacesRepository()

        _remember(repository, "井戸")
        _remember(repository, "井戸")

        assert len(repository.get(GEN).places) == 1
