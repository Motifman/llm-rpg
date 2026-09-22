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

    def test_rotation_from_south_degrees_returns_none_for_vertical_directions(self):
        """UP と DOWN は平面上の回転角を持たないので None を返し、SOUTH の 0.0 と区別できる。"""
        assert Facing.from_direction(DirectionEnum.UP).rotation_from_south_degrees() is None
        assert Facing.from_direction(DirectionEnum.DOWN).rotation_from_south_degrees() is None
        assert Facing.from_direction(DirectionEnum.SOUTH).rotation_from_south_degrees() == 0.0

    def test_rotation_from_south_degrees_returns_a_multiple_of_45_for_every_compass_direction(self):
        """8 方位はいずれも回転角を持ち、その値は 45 度の倍数になる。"""
        compass = [
            DirectionEnum.NORTH,
            DirectionEnum.NORTHEAST,
            DirectionEnum.EAST,
            DirectionEnum.SOUTHEAST,
            DirectionEnum.SOUTH,
            DirectionEnum.SOUTHWEST,
            DirectionEnum.WEST,
            DirectionEnum.NORTHWEST,
        ]
        for direction in compass:
            degrees = Facing.from_direction(direction).rotation_from_south_degrees()
            assert degrees is not None
            assert degrees % 45.0 == 0.0
