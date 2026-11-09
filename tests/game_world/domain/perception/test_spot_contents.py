from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.object_and_item import NoLook
from ai_rpg_world.game_world.domain.exception.surroundings_exception import (
    HeldItemNotCarriedException,
    ThingFromAnotherSpotException,
    UnrevealedThingNotDeclaredHiddenException,
)
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonHandle, PersonRef
from ai_rpg_world.game_world.domain.perception.surroundings import ContainedObject, ContainedPassage, PresentPerson
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


class TestOnlyHiddenThingsCanBeUnrevealed:
    """ContainedObject と ContainedPassage が、隠れていると宣言されていない物を「現れていない」として受け取らないことを保証する。"""

    def test_unrevealed_object_not_declared_hidden_is_refused(self) -> None:
        """hidden_until_revealed が偽の物体を revealed=False で入れると、UnrevealedThingNotDeclaredHiddenException を投げる。"""
        declaration = thing("ore_cart").declaration

        with pytest.raises(UnrevealedThingNotDeclaredHiddenException):
            ContainedObject(declaration=declaration, revealed=False, look=NoLook())

    def test_unrevealed_passage_not_declared_hidden_is_refused(self) -> None:
        """hidden_until_revealed が偽の通路を revealed=False で入れると、UnrevealedThingNotDeclaredHiddenException を投げる。"""
        in_state = passage("corridor").passage

        with pytest.raises(UnrevealedThingNotDeclaredHiddenException):
            ContainedPassage(passage=in_state, revealed=False)

    def test_revealed_hidden_object_is_accepted(self) -> None:
        """hidden_until_revealed が真の物体は、現れたあと revealed=True で受け取る。"""
        declaration = thing("hidden_door", revealed=False).declaration

        assert ContainedObject(declaration=declaration, revealed=True, look=NoLook()).revealed
