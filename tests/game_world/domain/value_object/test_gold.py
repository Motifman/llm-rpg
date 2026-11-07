from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    InsufficientGoldException,
    ValueOutOfRangeException,
)
from ai_rpg_world.game_world.domain.value_object import Gold


class TestGold:
    """Gold が 0 以上の所持金を表し、稼ぐ (足す)・払う (引く)・比べるができ、持っている額を超える支払いを断ることを保証する。"""

    def test_zero_is_accepted_for_no_money(self) -> None:
        """一文無しを表す 0 を受け付ける。"""
        assert Gold(0) == Gold(0)

    def test_negative_raises_domain_exception(self) -> None:
        """負の額を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Gold(-1)

    @pytest.mark.parametrize("raw", [1.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Gold(raw)  # type: ignore[arg-type]

    def test_earning_adds_to_the_amount(self) -> None:
        """Gold どうしを足すと合計の額になる (PersonInventory.earn)。"""
        assert Gold(10) + Gold(5) == Gold(15)

    def test_paying_the_whole_amount_leaves_zero(self) -> None:
        """持っている額ちょうどを引くと Gold(0) になる (PersonInventory.pay)。"""
        assert Gold(10) - Gold(10) == Gold(0)

    def test_paying_more_than_held_raises_domain_exception(self) -> None:
        """持っている額より多く引くと InsufficientGoldException を投げる。"""
        with pytest.raises(InsufficientGoldException):
            Gold(10) - Gold(11)

    def test_amounts_compare_for_gold_at_least(self) -> None:
        """GoldAtLeastCondition のため、額どうしを大小で比べられる。"""
        assert Gold(10) >= Gold(10)
        assert not Gold(9) >= Gold(10)
