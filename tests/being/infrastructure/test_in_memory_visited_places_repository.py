from __future__ import annotations

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_visited_places_repository import InMemoryVisitedPlacesRepository

GEN = BeingId("being_gen")


class TestInMemoryVisitedPlacesRepository:
    """InMemoryVisitedPlacesRepository が、保存した記録だけを返し、出し入れのたびに写しを渡すことを保証する。"""

    def test_saved_visit_is_returned(self) -> None:
        """訪れた記録を保存すると、次に取り出したときも訪れたことになる。"""
        repository = InMemoryVisitedPlacesRepository()
        places = repository.get(GEN)
        places.visit(environment_name="廃坑の山村", place="井戸")

        repository.save(places)

        assert repository.get(GEN).has_visited(environment_name="廃坑の山村", place="井戸")

    def test_visit_without_save_is_not_stored(self) -> None:
        """取り出した記録に訪れたことを足しても、保存しなければ保存先は変わらない。"""
        repository = InMemoryVisitedPlacesRepository()

        repository.get(GEN).visit(environment_name="廃坑の山村", place="井戸")

        assert not repository.get(GEN).has_visited(environment_name="廃坑の山村", place="井戸")
