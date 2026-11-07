from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    CountBelowZeroException,
    ValueOutOfRangeException,
)
from ai_rpg_world.game_world.domain.value_object import Count


class TestCount:
    """Count が 0 以上の個数を表し、足す・引く・比べるができ、0 を下回る引き算を断ることを保証する。"""

    def test_zero_is_accepted_for_nothing_held_or_searched(self) -> None:
        """持っていない・探していないことを表す 0 を受け付ける (item_count、search_count)。"""
        assert Count(0).value == 0

    def test_negative_raises_domain_exception(self) -> None:
        """負の値を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Count(-1)

    @pytest.mark.parametrize("raw", [2.0, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Count(raw)  # type: ignore[arg-type]

    def test_adding_counts_sums_them(self) -> None:
        """Count どうしを足すと合計の Count になる (ObjectState.add_to_count)。"""
        assert Count(2) + Count(3) == Count(5)

    def test_subtracting_down_to_zero_is_allowed(self) -> None:
        """持っている数ちょうどを引くと Count(0) になる (SubtractFromObjectCountEffect、take_from_stock)。"""
        assert Count(3) - Count(3) == Count(0)

    def test_subtracting_more_than_held_raises_domain_exception(self) -> None:
        """今の数より多く引くと CountBelowZeroException を投げる。"""
        with pytest.raises(CountBelowZeroException):
            Count(2) - Count(3)

    def test_counts_compare_for_at_least_conditions(self) -> None:
        """HasItemCondition などの「以上」のため、Count どうしを大小で比べられる。"""
        assert Count(3) >= Count(3)
        assert not Count(2) >= Count(3)
