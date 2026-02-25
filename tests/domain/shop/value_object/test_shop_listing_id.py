"""ShopListingId値オブジェクトのテスト"""
import pytest
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.exception.shop_exception import ShopListingIdValidationException


class TestShopListingId:
    """ShopListingId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        listing_id = ShopListingId(1)
        assert listing_id.value == 1

    def test_create_from_int_create_method(self):
        """createメソッドでintから作成できること"""
        listing_id = ShopListingId.create(123)
        assert listing_id.value == 123
        assert isinstance(listing_id, ShopListingId)

    def test_create_from_str_create_method(self):
        """createメソッドでstrから作成できること"""
        listing_id = ShopListingId.create("456")
        assert listing_id.value == 456

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(ShopListingIdValidationException):
            ShopListingId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(ShopListingIdValidationException):
            ShopListingId(-1)

    def test_create_from_invalid_str_raises_error(self):
        """無効な文字列から作成できないこと"""
        with pytest.raises(ShopListingIdValidationException):
            ShopListingId.create("abc")

    def test_equality_and_hash(self):
        """等価性とハッシュが正しく動作すること"""
        a = ShopListingId(1)
        b = ShopListingId(1)
        c = ShopListingId(2)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
