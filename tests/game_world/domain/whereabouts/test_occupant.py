from __future__ import annotations

from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, PersonBody


class TestCanHoldItems:
    """居場所を持つもののうち、体だけが品物を手に持てることを保証する。"""

    def test_body_can_hold_items(self) -> None:
        """人の体 (PersonBody) は品物を手に持てる。"""
        assert PersonBody(PersonId("alice")).can_hold_items()

    def test_departed_person_cannot_hold_items(self) -> None:
        """去った人 (DepartedPerson) には手が無く、品物を持てない。"""
        assert not DepartedPerson(PersonId("alice")).can_hold_items()
