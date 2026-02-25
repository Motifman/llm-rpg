"""ShopListingPrice値オブジェクトのテスト"""
import pytest
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.exception.shop_exception import ShopListingPriceValidationException


class TestShopListingPrice:
    """ShopListingPrice値オブジェクトのテスト"""

    def test_create_positive_value(self):
        """1以上の値で作成できること"""
        price = ShopListingPrice.of(1)
        assert price.value == 1
        price = ShopListingPrice.of(100)
        assert price.value == 100

    def test_of_factory_method(self):
        """ofファクトリメソッドで作成できること"""
        price = ShopListingPrice.of(50)
        assert price.value == 50
        assert isinstance(price, ShopListingPrice)

    def test_zero_raises_error(self):
        """0は作成できないこと"""
        with pytest.raises(ShopListingPriceValidationException):
            ShopListingPrice.of(0)

    def test_negative_raises_error(self):
        """負の値は作成できないこと"""
        with pytest.raises(ShopListingPriceValidationException):
            ShopListingPrice.of(-1)

    def test_str_repr(self):
        """文字列表現が正しいこと"""
        price = ShopListingPrice.of(99)
        assert "99" in str(price)
        assert "ShopListingPrice" in repr(price) or "99" in repr(price)

    def test_int_conversion(self):
        """int変換が正しく動作すること"""
        price = ShopListingPrice.of(42)
        assert int(price) == 42

    def test_equality_and_hash(self):
        """等価性とハッシュが正しく動作すること"""
        a = ShopListingPrice.of(10)
        b = ShopListingPrice.of(10)
        c = ShopListingPrice.of(20)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
