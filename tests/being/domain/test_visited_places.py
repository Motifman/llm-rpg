from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.visited_places import VisitedPlace, VisitedPlaces
from ai_rpg_world.domain.being.exception.being_exceptions import VisitedPlacesValidationException

GEN = BeingId("being_gen")


class TestVisitedPlaces:
    """VisitedPlaces が、Being が訪れた場所を、環境の名前ごとに覚えることを保証する。"""

    def test_place_not_visited_yet_is_unknown(self) -> None:
        """まだ訪れていない場所は、訪れたことにならない。"""
        assert not VisitedPlaces.empty(GEN).has_visited(environment_name="廃坑の山村", place="南の坑道")

    def test_visited_place_is_remembered(self) -> None:
        """訪れた場所は、同じ環境の名前で問えば、訪れたことになる。"""
        places = VisitedPlaces.empty(GEN)

        places.visit(environment_name="廃坑の山村", place="南の坑道")

        assert places.has_visited(environment_name="廃坑の山村", place="南の坑道")

    def test_same_place_name_in_another_environment_is_not_visited(self) -> None:
        """別の環境の同じ名前の場所は、訪れたことにならない。"""
        places = VisitedPlaces.empty(GEN)

        places.visit(environment_name="廃坑の山村", place="井戸")

        assert not places.has_visited(environment_name="遭難の島", place="井戸")

    def test_visiting_twice_keeps_one_record(self) -> None:
        """同じ場所を 2 回訪れても、記録は 1 件のまま。"""
        places = VisitedPlaces.empty(GEN)

        places.visit(environment_name="廃坑の山村", place="井戸")
        places.visit(environment_name="廃坑の山村", place="井戸")

        assert places.places == (VisitedPlace(environment_name="廃坑の山村", place="井戸"),)

    @pytest.mark.parametrize(("environment_name", "place"), [(" ", "井戸"), ("廃坑の山村", "")])
    def test_blank_name_is_rejected(self, environment_name: str, place: str) -> None:
        """環境の名前か場所の名前が空なら VisitedPlacesValidationException を投げ、何も覚えない。"""
        places = VisitedPlaces.empty(GEN)

        with pytest.raises(VisitedPlacesValidationException):
            places.visit(environment_name=environment_name, place=place)
        assert places.places == ()
