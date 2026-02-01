import pytest
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.exception.map_exception import CoordinateValidationException


class TestCoordinate:
    """Coordinate値オブジェクトのテスト"""

    def test_create_success(self):
        """正常に作成できること"""
        coord = Coordinate(10, 20, 1)
        assert coord.x == 10
        assert coord.y == 20
        assert coord.z == 1
        
    def test_create_default_z(self):
        """zのデフォルト値が0であること"""
        coord = Coordinate(10, 20)
        assert coord.z == 0

    def test_create_boundary_zero(self):
        """0の座標で作成できること"""
        coord = Coordinate(0, 0, 0)
        assert coord.x == 0
        assert coord.y == 0
        assert coord.z == 0

    def test_create_negative_raises_error(self):
        """x, yの負の座標は作成できないが、zは可能であること"""
        with pytest.raises(CoordinateValidationException):
            Coordinate(-1, 0, 0)
        with pytest.raises(CoordinateValidationException):
            Coordinate(0, -1, 0)
        
        # zは負の値（地下）を許容する
        coord = Coordinate(0, 0, -1)
        assert coord.z == -1

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        coord = Coordinate(5, 5, 2)
        assert str(coord) == "(5, 5, 2)"

    def test_distance_to(self):
        """マンハッタン距離が正しく計算されること（zの差も含む）"""
        c1 = Coordinate(0, 0, 0)
        c2 = Coordinate(3, 4, 2)
        assert c1.distance_to(c2) == 9 # 3 + 4 + 2
        assert c2.distance_to(c1) == 9

    def test_distance_to_z_axis(self):
        """z軸を考慮したマンハッタン距離が正しく計算されること"""
        c1 = Coordinate(0, 0, 0)
        c2 = Coordinate(0, 0, 5)
        assert c1.distance_to(c2) == 5
        
        c3 = Coordinate(1, 1, 1)
        c4 = Coordinate(2, 2, 2)
        assert c3.distance_to(c4) == 3 # |2-1| + |2-1| + |2-1| = 3

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        c1 = Coordinate(1, 2)
        c2 = Coordinate(1, 2)
        c3 = Coordinate(2, 1)

        assert c1 == c2
        assert c1 != c3
        assert c1 != (1, 2)

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        c1 = Coordinate(10, 10)
        c2 = Coordinate(10, 10)
        assert hash(c1) == hash(c2)
        assert len({c1, c2}) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        coord = Coordinate(1, 1)
        with pytest.raises(AttributeError):
            coord.x = 2
        with pytest.raises(AttributeError):
            coord.y = 2
