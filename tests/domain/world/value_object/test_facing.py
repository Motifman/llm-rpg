from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
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
