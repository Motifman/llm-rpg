from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.exception.character_exception import HeldItemNotAmongInitialItemsException
from ai_rpg_world.game_world.domain.value_object import DescriptionText, GroupId, ItemSpecId, PersonId, SpotId

_LANTERN = ItemSpecId("lantern")
_PICKAXE = ItemSpecId("pickaxe")
_ROPE = ItemSpecId("rope")


def _character(
    initial_items: tuple[ItemSpecId, ...],
    initial_held: tuple[ItemSpecId, ...],
) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=PersonId("miner"),
        appearance=DescriptionText("煤けた作業着の男"),
        spawn_spot=SpotId("lift_landing"),
        initial_items=initial_items,
        initial_held=initial_held,
        initial_groups=(GroupId("miners"),),
        knows_at_start=(PersonId("foreman"),),
    )


class TestInitialHeld:
    """CharacterDeclaration.initial_held が、initial_items のうち最初から手に持っている物だけを表すことを保証する。"""

    def test_held_items_taken_from_initial_items_are_accepted(self) -> None:
        """initial_held の品物がどれも initial_items にあれば作れ、宣言した順のまま持つ。"""
        character = _character(initial_items=(_LANTERN, _ROPE, _PICKAXE), initial_held=(_PICKAXE, _LANTERN))

        assert character.initial_held == (_PICKAXE, _LANTERN)

    def test_nothing_held_is_accepted(self) -> None:
        """initial_held が空なら、initial_items が何であっても作れる。"""
        character = _character(initial_items=(_LANTERN,), initial_held=())

        assert character.initial_held == ()

    def test_held_item_missing_from_initial_items_is_rejected(self) -> None:
        """initial_held に initial_items に無い品物があると HeldItemNotAmongInitialItemsException を投げる。"""
        with pytest.raises(HeldItemNotAmongInitialItemsException):
            _character(initial_items=(_ROPE,), initial_held=(_LANTERN,))

    def test_holding_more_copies_than_carried_is_rejected(self) -> None:
        """initial_items に 1 つしか無い品物を initial_held で 2 つ手に持つと HeldItemNotAmongInitialItemsException を投げる。"""
        with pytest.raises(HeldItemNotAmongInitialItemsException):
            _character(initial_items=(_LANTERN, _ROPE), initial_held=(_LANTERN, _LANTERN))

    def test_holding_as_many_copies_as_carried_is_accepted(self) -> None:
        """initial_items に 2 つある品物は、initial_held で 2 つとも手に持てる。"""
        character = _character(initial_items=(_LANTERN, _LANTERN), initial_held=(_LANTERN, _LANTERN))

        assert character.initial_held == (_LANTERN, _LANTERN)
