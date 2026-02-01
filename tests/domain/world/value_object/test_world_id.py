import pytest
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.exception.map_exception import WorldIdValidationException


class TestWorldId:
    """WorldId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        world_id = WorldId(1)
        assert world_id.value == 1

    def test_create_large_positive_int_id(self):
        """大きな正の整数値で作成できること"""
        world_id = WorldId(999999)
        assert world_id.value == 999999

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(WorldIdValidationException):
            WorldId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(WorldIdValidationException):
            WorldId(-1)

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        world_id = WorldId(789)
        assert str(world_id) == "789"

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        world_id1 = WorldId(202)
        world_id2 = WorldId(202)
        world_id3 = WorldId(303)

        assert world_id1 == world_id2
        assert world_id1 != world_id3
        assert world_id1 != "not a world id"
        assert world_id1 is not None

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        world_id1 = WorldId(404)
        world_id2 = WorldId(404)

        assert hash(world_id1) == hash(world_id2)

        # setで重複が除去されることを確認
        world_id_set = {world_id1, world_id2}
        assert len(world_id_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        world_id = WorldId(505)
        
        with pytest.raises(AttributeError):
            world_id.value = 606
