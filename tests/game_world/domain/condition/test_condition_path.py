from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException


class TestConditionPath:
    """ConditionPath が、条件の木の中の位置を根からの子の位置の並びで区別することを保証する。"""

    def test_same_steps_from_root_are_equal(self) -> None:
        """根から同じ順に子をたどった道筋どうしは等しく、同じ鍵として使える。"""
        first = ConditionPath.root().child(0).child(1)
        second = ConditionPath.root().child(0).child(1)

        assert first == second
        assert hash(first) == hash(second)

    def test_root_and_its_child_differ(self) -> None:
        """根と、根の最初の子は別の位置。"""
        assert ConditionPath.root() != ConditionPath.root().child(0)

    def test_siblings_differ(self) -> None:
        """同じ親の 1 番目の子と 2 番目の子は別の位置。"""
        assert ConditionPath.root().child(0) != ConditionPath.root().child(1)

    def test_same_position_under_different_parents_differs(self) -> None:
        """親が違えば、同じ位置の子でも別の位置。"""
        assert ConditionPath.root().child(0).child(0) != ConditionPath.root().child(1).child(0)

    def test_negative_position_raises_domain_exception(self) -> None:
        """子の位置に負の数を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            ConditionPath.root().child(-1)
