"""ShopId値オブジェクトのテスト"""
import pytest
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.exception.shop_exception import ShopIdValidationException


class TestShopId:
    """ShopId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        shop_id = ShopId(1)
        assert shop_id.value == 1

    def test_create_large_positive_int_id(self):
        """大きな正の整数値で作成できること"""
        shop_id = ShopId(999999)
        assert shop_id.value == 999999

    def test_create_from_int_create_method(self):
        """createメソッドでintから作成できること"""
        shop_id = ShopId.create(123)
        assert shop_id.value == 123
        assert isinstance(shop_id, ShopId)

    def test_create_from_str_create_method(self):
        """createメソッドでstrから作成できること"""
        shop_id = ShopId.create("456")
        assert shop_id.value == 456
        assert isinstance(shop_id, ShopId)

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(ShopIdValidationException):
            ShopId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(ShopIdValidationException):
            ShopId(-1)
        with pytest.raises(ShopIdValidationException):
            ShopId(-100)

    def test_create_from_negative_str_raises_error(self):
        """負の文字列から作成できないこと"""
        with pytest.raises(ShopIdValidationException):
            ShopId.create("-5")

    def test_create_from_zero_str_raises_error(self):
        """0の文字列から作成できないこと"""
        with pytest.raises(ShopIdValidationException):
            ShopId.create("0")

    def test_create_from_invalid_str_raises_error(self):
        """無効な文字列から作成できないこと"""
        with pytest.raises(ShopIdValidationException):
            ShopId.create("abc")
        with pytest.raises(ShopIdValidationException):
            ShopId.create("12.5")
        with pytest.raises(ShopIdValidationException):
            ShopId.create("")

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        shop_id = ShopId(789)
        assert str(shop_id) == "789"

    def test_int_conversion(self):
        """int変換が正しく動作すること"""
        shop_id = ShopId(101)
        assert int(shop_id) == 101

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        shop_id1 = ShopId(202)
        shop_id2 = ShopId(202)
        shop_id3 = ShopId(303)
        assert shop_id1 == shop_id2
        assert shop_id1 != shop_id3
        assert shop_id1 != "not a shop id"
        assert shop_id1 != 202

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        shop_id1 = ShopId(404)
        shop_id2 = ShopId(404)
        assert hash(shop_id1) == hash(shop_id2)
        shop_id_set = {shop_id1, shop_id2}
        assert len(shop_id_set) == 1
