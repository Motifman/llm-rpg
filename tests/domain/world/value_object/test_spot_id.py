import pytest
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.exception.map_exception import SpotIdValidationException


class TestSpotId:
    """SpotId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        spot_id = SpotId(1)
        assert spot_id.value == 1

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(SpotIdValidationException):
            SpotId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(SpotIdValidationException):
            SpotId(-1)

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        spot_id = SpotId(789)
        assert str(spot_id) == "789"

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        spot_id1 = SpotId(202)
        spot_id2 = SpotId(202)
        spot_id3 = SpotId(303)

        assert spot_id1 == spot_id2
        assert spot_id1 != spot_id3
        assert spot_id1 != "not a spot id"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        spot_id1 = SpotId(404)
        spot_id2 = SpotId(404)

        assert hash(spot_id1) == hash(spot_id2)

        # setで重複が除去されることを確認
        spot_id_set = {spot_id1, spot_id2}
        assert len(spot_id_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        spot_id = SpotId(505)
        
        with pytest.raises(AttributeError):
            spot_id.value = 606
