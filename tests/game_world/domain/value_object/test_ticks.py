from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import Ticks


class TestTicks:
    """Ticks が 0 以上の tick の長さだけを表し、長さどうしで比べられることを保証する。"""

    def test_zero_is_accepted_because_death_grace_may_be_zero(self) -> None:
        """DeathRule.grace に使う 0 (倒れたらすぐ死ぬ) を受け付ける。"""
        assert Ticks(0) == Ticks(0)

    def test_negative_raises_domain_exception(self) -> None:
        """負の値を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Ticks(-1)

    @pytest.mark.parametrize("raw", [1.5, True, "3"])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値、文字列) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Ticks(raw)  # type: ignore[arg-type]

    def test_longer_ticks_is_at_least_shorter(self) -> None:
        """TicksInWorldStageAtLeastCondition のため、長さどうしを大小で比べられる。"""
        assert Ticks(3) >= Ticks(3)
        assert Ticks(4) > Ticks(3)
        assert not Ticks(2) >= Ticks(3)
