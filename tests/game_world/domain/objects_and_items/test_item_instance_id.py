from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.world_design_exception import BlankDeclaredNameException
from ai_rpg_world.game_world.domain.objects_and_items import ItemInstanceId


class TestItemInstanceId:
    """ItemInstanceId が、世界にある品物 1 つを空でない文字列で指すことを保証する。"""

    def test_keeps_the_given_name(self) -> None:
        """空でない文字列を渡すと、その文字列をそのまま持つ。"""
        item_id = ItemInstanceId("lantern#1")

        assert item_id.value == "lantern#1"

    @pytest.mark.parametrize("value", ["", "   ", None, 1])
    def test_rejects_blank_or_non_str(self, value: object) -> None:
        """空、空白だけ、文字列でない値を渡すと BlankDeclaredNameException を投げる。"""
        with pytest.raises(BlankDeclaredNameException):
            ItemInstanceId(value)  # type: ignore[arg-type]

    def test_ids_with_same_name_are_equal(self) -> None:
        """同じ文字列の ItemInstanceId どうしは等しく、違えば等しくない。"""
        assert ItemInstanceId("lantern#1") == ItemInstanceId("lantern#1")
        assert ItemInstanceId("lantern#1") != ItemInstanceId("lantern#2")
