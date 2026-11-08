from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException


class TestConditionPath:
    """ConditionPath が、子の返した位置を親が自分の番号で包んで作った位置を、包んだ番号と順で区別することを保証する。"""

    def test_same_wrapping_gives_equal_positions(self) -> None:
        """根を 1 で包み、さらに 0 で包んだ位置を 2 回作ると、等しく、同じ鍵として使える。"""
        first = ConditionPath.root().under(1).under(0)
        second = ConditionPath.root().under(1).under(0)

        assert first == second
        assert hash(first) == hash(second)

    def test_order_of_wrapping_matters(self) -> None:
        """0 で包んでから 1 で包んだ位置と、1 で包んでから 0 で包んだ位置は別の位置。"""
        assert ConditionPath.root().under(0).under(1) != ConditionPath.root().under(1).under(0)

    def test_root_and_a_wrapped_position_differ(self) -> None:
        """根と、根を 0 で包んだ位置は別の位置。"""
        assert ConditionPath.root() != ConditionPath.root().under(0)

    def test_siblings_differ(self) -> None:
        """同じ親が 0 で包んだ子と 1 で包んだ子は別の位置。"""
        assert ConditionPath.root().under(0) != ConditionPath.root().under(1)

    def test_negative_position_raises_domain_exception(self) -> None:
        """位置に負の数を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            ConditionPath.root().under(-1)
