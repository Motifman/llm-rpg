from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.exception.character_exception import (
    DuplicatedInitialGroupException,
    DuplicatedKnownPersonException,
    HeldItemNotAmongInitialItemsException,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, GroupId, ItemSpecId, PersonId, SpotId

_LANTERN = ItemSpecId("lantern")
_PICKAXE = ItemSpecId("pickaxe")
_ROPE = ItemSpecId("rope")


def _character(
    initial_items: tuple[ItemSpecId, ...],
    initial_held: tuple[ItemSpecId, ...],
    initial_groups: tuple[GroupId, ...] = (GroupId("miners"),),
    knows_at_start: tuple[PersonId, ...] = (PersonId("foreman"),),
) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=PersonId("miner"),
        appearance=DescriptionText("煤けた作業着の男"),
        spawn_spot=SpotId("lift_landing"),
        initial_items=initial_items,
        initial_held=initial_held,
        initial_groups=initial_groups,
        knows_at_start=knows_at_start,
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


class TestNoDuplicatesWithinDeclaration:
    """CharacterDeclaration の initial_groups と knows_at_start が、同じものを 2 度挙げないことを保証する。"""

    def test_same_group_listed_twice_is_rejected(self) -> None:
        """initial_groups に同じ GroupId が 2 回あると DuplicatedInitialGroupException を投げる。"""
        with pytest.raises(DuplicatedInitialGroupException):
            _character(initial_items=(), initial_held=(), initial_groups=(GroupId("miners"), GroupId("miners")))

    def test_distinct_groups_are_accepted(self) -> None:
        """initial_groups の GroupId がどれも違えば作れ、宣言した順のまま持つ。"""
        groups = (GroupId("miners"), GroupId("night_shift"))

        assert _character(initial_items=(), initial_held=(), initial_groups=groups).initial_groups == groups

    def test_same_person_known_twice_is_rejected(self) -> None:
        """knows_at_start に同じ PersonId が 2 回あると DuplicatedKnownPersonException を投げる。"""
        with pytest.raises(DuplicatedKnownPersonException):
            _character(initial_items=(), initial_held=(), knows_at_start=(PersonId("foreman"), PersonId("foreman")))

    def test_distinct_known_people_are_accepted(self) -> None:
        """knows_at_start の PersonId がどれも違えば作れ、宣言した順のまま持つ。"""
        people = (PersonId("foreman"), PersonId("doctor"))

        assert _character(initial_items=(), initial_held=(), knows_at_start=people).knows_at_start == people
