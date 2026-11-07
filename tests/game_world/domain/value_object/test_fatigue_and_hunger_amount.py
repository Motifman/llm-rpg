from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import FatigueAmount, HungerAmount


class TestFatigueAmount:
    """FatigueAmount が 0 以上の疲れの量を表し、積み増して限界と比べられることを保証する。"""

    def test_zero_is_accepted_for_no_fatigue(self) -> None:
        """疲れていないことを表す 0 を受け付ける。"""
        assert FatigueAmount(0) == FatigueAmount(0)

    def test_negative_raises_domain_exception(self) -> None:
        """負の値を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            FatigueAmount(-1)

    @pytest.mark.parametrize("raw", [2.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            FatigueAmount(raw)  # type: ignore[arg-type]

    def test_exertion_adds_to_fatigue(self) -> None:
        """疲れに FatigueRule.per_exertion の 2 を足すと 2 増える。"""
        assert FatigueAmount(98) + FatigueAmount(2) == FatigueAmount(100)

    def test_fatigue_compares_with_the_limit(self) -> None:
        """限界 (FatigueRule.limit) に達したかを大小で比べられる。"""
        assert FatigueAmount(100) >= FatigueAmount(100)
        assert not FatigueAmount(99) >= FatigueAmount(100)


class TestHungerAmount:
    """HungerAmount が 0 以上の空腹の量を表し、積み増して限界と比べられることを保証する。"""

    def test_zero_is_accepted_for_no_hunger(self) -> None:
        """空腹でないことを表す 0 を受け付ける。"""
        assert HungerAmount(0) == HungerAmount(0)

    def test_negative_raises_domain_exception(self) -> None:
        """負の値を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HungerAmount(-1)

    @pytest.mark.parametrize("raw", [0.5, False])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HungerAmount(raw)  # type: ignore[arg-type]

    def test_passing_time_adds_to_hunger(self) -> None:
        """空腹に HungerRule.per_tick の 1 を足すと 1 増える。"""
        assert HungerAmount(5) + HungerAmount(1) == HungerAmount(6)

    def test_hunger_compares_with_the_limit(self) -> None:
        """限界 (HungerRule.limit) に達したかと、HungerAtLeastCondition のため大小で比べられる。"""
        assert HungerAmount(50) >= HungerAmount(50)
        assert not HungerAmount(49) >= HungerAmount(50)
