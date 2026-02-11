import pytest
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException

class TestHitBoxShape:
    def test_single_cell(self):
        shape = HitBoxShape.single_cell()
        origin = Coordinate(10, 10, 0)
        absolute = shape.to_absolute(origin)
        assert len(absolute) == 1
        assert absolute[0] == origin

    def test_cross(self):
        shape = HitBoxShape.cross()
        origin = Coordinate(5, 5, 0)
        absolute = shape.to_absolute(origin)
        # origin (5,5,0), (5,6,0), (5,4,0), (6,5,0), (4,5,0)
        assert len(absolute) == 5
        assert Coordinate(5, 5, 0) in absolute
        assert Coordinate(5, 6, 0) in absolute
        assert Coordinate(5, 4, 0) in absolute
        assert Coordinate(6, 5, 0) in absolute
        assert Coordinate(4, 5, 0) in absolute

    def test_absolute_out_of_bounds_skips(self):
        # 原点が (0,0,0) の場合、マイナスの相対座標は除外される
        shape = HitBoxShape.cross()
        origin = Coordinate(0, 0, 0)
        absolute = shape.to_absolute(origin)
        # (0,0), (0,1), (1,0) のみが残るはず（(0,-1), (-1,0) は除外）
        assert len(absolute) == 3
        assert Coordinate(0, 0, 0) in absolute
        assert Coordinate(0, 1, 0) in absolute
        assert Coordinate(1, 0, 0) in absolute

    def test_empty_fails(self):
        with pytest.raises(HitBoxValidationException):
            HitBoxShape(relative_coordinates=[])
