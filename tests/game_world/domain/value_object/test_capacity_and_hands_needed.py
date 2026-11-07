from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import Capacity, HandsNeeded


class TestCapacity:
    """Capacity が 1 以上の定員だけを表すことを保証する。定員の無い区画は NoCapacity で書く。"""

    def test_one_is_the_smallest_capacity(self) -> None:
        """1 人乗りの区画を表す 1 を受け付ける。"""
        assert Capacity(1) == Capacity(1)

    @pytest.mark.parametrize("raw", [0, -1])
    def test_zero_or_negative_raises_domain_exception(self, raw: int) -> None:
        """誰も入れない 0 や負の定員は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Capacity(raw)

    @pytest.mark.parametrize("raw", [1.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Capacity(raw)  # type: ignore[arg-type]


class TestHandsNeeded:
    """HandsNeeded が 1 (カンテラ) か 2 (つるはし) だけを表すことを保証する。"""

    @pytest.mark.parametrize("raw", [1, 2])
    def test_one_or_two_hands_are_accepted(self, raw: int) -> None:
        """1 と 2 を受け付ける。"""
        assert HandsNeeded(raw) == HandsNeeded(raw)

    @pytest.mark.parametrize("raw", [0, 3, -1])
    def test_other_numbers_raise_domain_exception(self, raw: int) -> None:
        """手は 2 本なので、0 や 3 は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HandsNeeded(raw)

    @pytest.mark.parametrize("raw", [True, 1.0])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """真偽値や小数の 1 は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HandsNeeded(raw)  # type: ignore[arg-type]
