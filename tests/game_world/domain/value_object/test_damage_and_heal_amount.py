from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import Damage, HealAmount


class TestDamage:
    """Damage が 1 以上の痛手だけを表すことを保証する。痛手の無い世界は Damage ではなく NoStarvationDamage で書く。"""

    def test_one_is_the_smallest_damage(self) -> None:
        """1 を受け付ける。"""
        assert Damage(1) == Damage(1)

    @pytest.mark.parametrize("raw", [0, -1])
    def test_zero_or_negative_raises_domain_exception(self, raw: int) -> None:
        """0 や負の痛手は宣言の書き間違いとして ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Damage(raw)

    @pytest.mark.parametrize("raw", [1.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Damage(raw)  # type: ignore[arg-type]


class TestHealAmount:
    """HealAmount が 1 以上の回復量だけを表すことを保証する。"""

    def test_one_is_the_smallest_heal(self) -> None:
        """1 を受け付ける。"""
        assert HealAmount(1) == HealAmount(1)

    @pytest.mark.parametrize("raw", [0, -1])
    def test_zero_or_negative_raises_domain_exception(self, raw: int) -> None:
        """0 や負の回復量は宣言の書き間違いとして ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HealAmount(raw)

    @pytest.mark.parametrize("raw", [1.5, True])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HealAmount(raw)  # type: ignore[arg-type]
