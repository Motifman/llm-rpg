from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import Damage, HealAmount, HitPoints


class TestHitPointsRange:
    """HitPoints が今の値 (0 以上) と最大値 (1 以上) の組で、今の値が最大値を超えないことを保証する。"""

    def test_zero_current_is_accepted_for_a_fallen_person(self) -> None:
        """倒れた人を表す今の値 0 を受け付ける。"""
        assert HitPoints(current=0, maximum=10) == HitPoints(current=0, maximum=10)

    def test_full_hit_points_are_accepted(self) -> None:
        """今の値が最大値と等しい組を受け付ける。"""
        assert HitPoints(current=10, maximum=10) == HitPoints(current=10, maximum=10)

    def test_negative_current_raises_domain_exception(self) -> None:
        """今の値が負なら ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HitPoints(current=-1, maximum=10)

    def test_zero_maximum_raises_domain_exception(self) -> None:
        """最大値が 0 なら ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HitPoints(current=0, maximum=0)

    def test_current_above_maximum_raises_domain_exception(self) -> None:
        """今の値が最大値を超えると ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HitPoints(current=11, maximum=10)

    @pytest.mark.parametrize(("current", "maximum"), [(1.5, 10), (5, 10.0), (True, 10)])
    def test_non_integer_raises_domain_exception(self, current: object, maximum: object) -> None:
        """今の値か最大値が整数でない (小数、真偽値) と ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            HitPoints(current=current, maximum=maximum)  # type: ignore[arg-type]


class TestHitPointsDamageAndHeal:
    """HitPoints が Damage で減って 0 で止まり、HealAmount で増えて最大値で止まり、最大値は変わらないことを保証する。"""

    def test_damage_reduces_current(self) -> None:
        """Damage(3) を受けると今の値が 3 減る。"""
        assert HitPoints(current=10, maximum=10).damaged_by(Damage(3)) == HitPoints(current=7, maximum=10)

    def test_damage_beyond_current_stops_at_zero(self) -> None:
        """今の値より大きい Damage を受けても、今の値は 0 で止まる。"""
        assert HitPoints(current=2, maximum=10).damaged_by(Damage(5)) == HitPoints(current=0, maximum=10)

    def test_heal_raises_current(self) -> None:
        """HealAmount(3) で今の値が 3 増える。"""
        assert HitPoints(current=4, maximum=10).healed_by(HealAmount(3)) == HitPoints(current=7, maximum=10)

    def test_heal_beyond_maximum_stops_at_maximum(self) -> None:
        """最大値までの差より大きい HealAmount でも、今の値は最大値で止まる。"""
        assert HitPoints(current=8, maximum=10).healed_by(HealAmount(5)) == HitPoints(current=10, maximum=10)
