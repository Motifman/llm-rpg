from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.world_id_exception import BlankWorldIdException
from ai_rpg_world.game_world.domain.value_object import WorldId


class TestWorldId:
    """WorldId が、世界に 1 つの集約の持ち主となる世界を、空でない名前で指すことを保証する。"""

    def test_keeps_the_given_name(self) -> None:
        """空でない名前を渡すと、その文字列をそのまま持つ。"""
        world_id = WorldId("abandoned_mine_village")

        assert world_id.value == "abandoned_mine_village"

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_rejects_blank_or_non_str(self, value: object) -> None:
        """空、空白だけ、文字列でない値を渡すと BlankWorldIdException を投げる。"""
        with pytest.raises(BlankWorldIdException):
            WorldId(value)  # type: ignore[arg-type]

    def test_ids_with_same_name_are_equal(self) -> None:
        """同じ名前の WorldId どうしは等しく、違う名前なら等しくない。"""
        assert WorldId("a") == WorldId("a")
        assert WorldId("a") != WorldId("b")
