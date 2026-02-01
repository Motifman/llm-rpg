import pytest
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.exception.map_exception import WorldObjectIdValidationException


class TestWorldObjectId:
    """WorldObjectId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        obj_id = WorldObjectId(1)
        assert obj_id.value == 1

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(WorldObjectIdValidationException):
            WorldObjectId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(WorldObjectIdValidationException):
            WorldObjectId(-1)

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        obj_id = WorldObjectId(789)
        assert str(obj_id) == "789"

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        id1 = WorldObjectId(202)
        id2 = WorldObjectId(202)
        id3 = WorldObjectId(303)

        assert id1 == id2
        assert id1 != id3

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        id1 = WorldObjectId(404)
        id2 = WorldObjectId(404)
        assert hash(id1) == hash(id2)
        assert len({id1, id2}) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        obj_id = WorldObjectId(505)
        with pytest.raises(AttributeError):
            obj_id.value = 606
