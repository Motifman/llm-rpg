import pytest

from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.exception.map_exception import SameCoordinateDirectionException
from ai_rpg_world.domain.world.value_object.facing import Facing


class TestFacing:
    def test_from_delta_returns_diagonal_direction(self):
        facing = Facing.from_delta(3, -2)
        assert facing.to_direction() == DirectionEnum.NORTHEAST

    def test_to_display_label_for_diagonal(self):
        facing = Facing.from_direction(DirectionEnum.NORTHWEST)
        assert facing.to_display_label() == "北西"

    def test_to_delta_for_southwest(self):
        facing = Facing.from_direction(DirectionEnum.SOUTHWEST)
        assert facing.to_delta() == (-1, 1, 0)

    def test_rotation_from_south_degrees(self):
        facing = Facing.from_direction(DirectionEnum.EAST)
        assert facing.rotation_from_south_degrees() == -90.0

    def test_from_delta_with_zero_displacement_raises_domain_exception(self):
        """変位がゼロの from_delta は、組み込みの KeyError ではなくドメイン例外を投げる。"""
        with pytest.raises(SameCoordinateDirectionException):
            Facing.from_delta(0, 0, 0)

    def test_direction_enum_from_delta_with_zero_displacement_raises_domain_exception(self):
        """DirectionEnum 経由でも、変位がゼロなら同じドメイン例外になる。"""
        with pytest.raises(SameCoordinateDirectionException):
            DirectionEnum.from_delta(0, 0, 0)

    def test_from_delta_with_only_vertical_displacement_returns_up_or_down(self):
        """dx と dy がゼロでも dz があれば、例外にせず UP / DOWN を返す。"""
        assert Facing.from_delta(0, 0, 1).to_direction() == DirectionEnum.UP
        assert Facing.from_delta(0, 0, -1).to_direction() == DirectionEnum.DOWN
