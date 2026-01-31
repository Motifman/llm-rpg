import pytest
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.exception.trade_exception import TradeRequestedGoldValidationException


class TestTradeRequestedGold:
    """TradeRequestedGold値オブジェクトのテスト"""

    # ===== 正常系のテスト =====

    def test_create_with_positive_value(self):
        """正の値で作成できること"""
        gold = TradeRequestedGold(100)
        assert gold.value == 100

    def test_create_with_large_value(self):
        """大きな値で作成できること"""
        gold = TradeRequestedGold(999999)
        assert gold.value == 999999

    def test_create_with_one(self):
        """最小値の1で作成できること"""
        gold = TradeRequestedGold(1)
        assert gold.value == 1

    def test_create_with_of_method(self):
        """ofファクトリメソッドで作成できること"""
        gold = TradeRequestedGold.of(500)
        assert gold.value == 500
        assert isinstance(gold, TradeRequestedGold)

    # ===== 異常系のテスト =====

    def test_create_with_zero_raises_error(self):
        """0の値で作成できないこと"""
        with pytest.raises(TradeRequestedGoldValidationException):
            TradeRequestedGold(0)

    def test_create_with_negative_value_raises_error(self):
        """負の値で作成できないこと"""
        with pytest.raises(TradeRequestedGoldValidationException):
            TradeRequestedGold(-1)

        with pytest.raises(TradeRequestedGoldValidationException):
            TradeRequestedGold(-100)

    def test_create_with_of_method_zero_raises_error(self):
        """ofファクトリメソッドで0の値を作成できないこと"""
        with pytest.raises(TradeRequestedGoldValidationException):
            TradeRequestedGold.of(0)

    def test_create_with_of_method_negative_raises_error(self):
        """ofファクトリメソッドで負の値を作成できないこと"""
        with pytest.raises(TradeRequestedGoldValidationException):
            TradeRequestedGold.of(-50)

    # ===== 文字列変換メソッドのテスト =====

    def test_str_representation(self):
        """__str__メソッドが正しい文字列を返すこと"""
        gold = TradeRequestedGold(250)
        assert str(gold) == "250 G"

    def test_str_with_one(self):
        """1Gの場合の__str__表現"""
        gold = TradeRequestedGold(1)
        assert str(gold) == "1 G"

    def test_repr_representation(self):
        """__repr__メソッドが正しい文字列を返すこと"""
        gold = TradeRequestedGold(300)
        assert repr(gold) == "TradeRequestedGold(300)"

    # ===== 等価性とハッシュのテスト =====

    def test_equality_with_same_value(self):
        """同じ値のオブジェクトが等しいこと"""
        gold1 = TradeRequestedGold(200)
        gold2 = TradeRequestedGold(200)
        assert gold1 == gold2
        assert gold1 is not gold2  # 異なるインスタンス

    def test_equality_with_different_values(self):
        """異なる値のオブジェクトが等しくないこと"""
        gold1 = TradeRequestedGold(100)
        gold2 = TradeRequestedGold(200)
        assert gold1 != gold2

    def test_equality_with_non_trade_requested_gold(self):
        """異なる型のオブジェクトと比較するとFalseを返すこと"""
        gold = TradeRequestedGold(100)
        other = "not a gold object"
        assert (gold == other) is False

    def test_hash_consistency(self):
        """同じ値のオブジェクトは同じハッシュ値を持つこと"""
        gold1 = TradeRequestedGold(150)
        gold2 = TradeRequestedGold(150)
        assert hash(gold1) == hash(gold2)

    def test_hash_different_for_different_values(self):
        """異なる値のオブジェクトは異なるハッシュ値を持つこと"""
        gold1 = TradeRequestedGold(100)
        gold2 = TradeRequestedGold(200)
        assert hash(gold1) != hash(gold2)

    # ===== 不変性のテスト =====

    def test_immutability(self):
        """オブジェクトが不変であること"""
        gold = TradeRequestedGold(100)
        with pytest.raises(AttributeError):
            gold.value = 200  # frozen=Trueなので変更不可
