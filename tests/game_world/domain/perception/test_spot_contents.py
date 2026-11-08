from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.surroundings_exception import (
    HeldItemNotCarriedException,
    ThingFromAnotherSpotException,
)
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef
from ai_rpg_world.game_world.domain.perception.surroundings import PresentPerson
from ai_rpg_world.game_world.domain.value_object import DescriptionText
from ai_rpg_world.game_world.domain.whereabouts.location import OpenArea
from tests.game_world.domain.perception._surroundings_builders import contents, item, passage, section, thing


class TestPresentPersonItems:
    """PresentPerson が、手に持っている物を持ち物の中に限ることを保証する。"""

    def test_held_item_missing_from_all_items_is_refused(self) -> None:
        """手に持っている物が持ち物すべて (all_items) に無いと、HeldItemNotCarriedException を投げる。"""
        with pytest.raises(HeldItemNotCarriedException):
            PresentPerson(
                person=PersonRef(PersonHandle(1), DescriptionText("坑夫"), NoVisibleName()),
                section=OpenArea(),
                held_items=(item("pickaxe"),),
                all_items=(item("bread"),),
            )


class TestSpotContentsBelongToTheSpot:
    """SpotContents が、自分の場所のものではない物体・区画・通路を受け取らないことを保証する。"""

    def test_object_of_another_spot_is_refused(self) -> None:
        """別の場所に宣言された物体を入れると、ThingFromAnotherSpotException を投げる。"""
        with pytest.raises(ThingFromAnotherSpotException):
            contents(objects=(thing("well", at="village_square"),))

    def test_section_of_another_spot_is_refused(self) -> None:
        """別の場所の区画を入れると、ThingFromAnotherSpotException を投げる。"""
        with pytest.raises(ThingFromAnotherSpotException):
            contents(sections=(section("stall", at="village_square"),))

    def test_passage_not_ending_at_the_spot_is_refused(self) -> None:
        """どちらの端もこの場所ではない通路を入れると、ThingFromAnotherSpotException を投げる。"""
        with pytest.raises(ThingFromAnotherSpotException):
            contents(passages=(passage("road", at="village_square", to="mine_entrance"),))

    def test_passage_whose_far_end_is_the_spot_is_accepted(self) -> None:
        """通路の 2 つ目の端がこの場所であれば、受け取る。"""
        incoming = passage("ladder", at="mine_entrance", to="mine_depths")

        assert contents(passages=(incoming,)).passages == (incoming,)
