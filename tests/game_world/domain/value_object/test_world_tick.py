from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    TickOrderException,
    ValueOutOfRangeException,
)
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick


class TestWorldTick:
    """WorldTick が 0 から数える世界の時刻を表し、Ticks を足して進めることと、2 つの時刻の間の長さを求めることを保証する。"""

    def test_zero_is_the_first_tick(self) -> None:
        """世界の始まりの時刻 0 を受け付ける。"""
        assert WorldTick(0) == WorldTick(0)

    def test_negative_raises_domain_exception(self) -> None:
        """負の時刻を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            WorldTick(-1)

    @pytest.mark.parametrize("raw", [0.5, False])
    def test_non_integer_raises_domain_exception(self, raw: object) -> None:
        """整数でない値 (小数、真偽値) を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            WorldTick(raw)  # type: ignore[arg-type]

    def test_adding_ticks_advances_by_that_length(self) -> None:
        """WorldTick に Ticks を足すと、その長さだけ進んだ WorldTick になる (Down.fell_at + DeathRule.grace)。"""
        assert WorldTick(10) + Ticks(30) == WorldTick(40)

    def test_adding_zero_ticks_keeps_the_same_tick(self) -> None:
        """猶予 0 を足すと同じ時刻のまま (倒れた tick に死ぬ)。"""
        assert WorldTick(10) + Ticks(0) == WorldTick(10)

    def test_ticks_since_earlier_tick_is_the_elapsed_length(self) -> None:
        """後の時刻から前の時刻までの長さを Ticks で返す (Item.age、ticks_in_world_stage)。"""
        assert WorldTick(15).ticks_since(WorldTick(5)) == Ticks(10)

    def test_ticks_since_the_same_tick_is_zero(self) -> None:
        """同じ時刻からの長さは Ticks(0)。"""
        assert WorldTick(7).ticks_since(WorldTick(7)) == Ticks(0)

    def test_ticks_since_a_later_tick_raises_domain_exception(self) -> None:
        """まだ来ていない時刻からの長さを求めると TickOrderException を投げる。"""
        with pytest.raises(TickOrderException):
            WorldTick(5).ticks_since(WorldTick(6))

    def test_ticks_are_ordered_by_time(self) -> None:
        """TickAtLeastCondition と行っているあいだの判定のため、時刻どうしを大小で比べられる。"""
        assert WorldTick(5) < WorldTick(6)
        assert WorldTick(6) >= WorldTick(6)
