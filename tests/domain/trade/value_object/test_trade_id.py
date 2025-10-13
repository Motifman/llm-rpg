import pytest
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.exception.trade_exception import TradeIdValidationException


class TestTradeId:
    """TradeId値オブジェクトのテスト"""

    def test_create_positive_int_id(self):
        """正の整数値で作成できること"""
        trade_id = TradeId(1)
        assert trade_id.value == 1

    def test_create_large_positive_int_id(self):
        """大きな正の整数値で作成できること"""
        trade_id = TradeId(999999)
        assert trade_id.value == 999999

    def test_create_from_int_create_method(self):
        """createメソッドでintから作成できること"""
        trade_id = TradeId.create(123)
        assert trade_id.value == 123
        assert isinstance(trade_id, TradeId)

    def test_create_from_str_create_method(self):
        """createメソッドでstrから作成できること"""
        trade_id = TradeId.create("456")
        assert trade_id.value == 456
        assert isinstance(trade_id, TradeId)

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(TradeIdValidationException):
            TradeId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(TradeIdValidationException):
            TradeId(-1)

        with pytest.raises(TradeIdValidationException):
            TradeId(-100)

    def test_create_from_negative_str_raises_error(self):
        """負の文字列から作成できないこと"""
        with pytest.raises(TradeIdValidationException):
            TradeId.create("-5")

    def test_create_from_zero_str_raises_error(self):
        """0の文字列から作成できないこと"""
        with pytest.raises(TradeIdValidationException):
            TradeId.create("0")

    def test_create_from_invalid_str_raises_error(self):
        """無効な文字列から作成できないこと"""
        with pytest.raises(TradeIdValidationException):
            TradeId.create("abc")

        with pytest.raises(TradeIdValidationException):
            TradeId.create("12.5")

        with pytest.raises(TradeIdValidationException):
            TradeId.create("")

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        trade_id = TradeId(789)
        assert str(trade_id) == "789"

    def test_int_conversion(self):
        """int変換が正しく動作すること"""
        trade_id = TradeId(101)
        assert int(trade_id) == 101

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        trade_id1 = TradeId(202)
        trade_id2 = TradeId(202)
        trade_id3 = TradeId(303)

        assert trade_id1 == trade_id2
        assert trade_id1 != trade_id3
        assert trade_id1 != "not a trade id"
        assert trade_id1 != 202

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        trade_id1 = TradeId(404)
        trade_id2 = TradeId(404)

        assert hash(trade_id1) == hash(trade_id2)

        # setで重複が除去されることを確認
        trade_id_set = {trade_id1, trade_id2}
        assert len(trade_id_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        trade_id = TradeId(505)
        original_value = trade_id.value

        # 属性を直接変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            trade_id.value = 606

        # 元の値は変わっていないことを確認
        assert trade_id.value == original_value

    def test_create_method_with_zero_int_raises_error(self):
        """createメソッドで0のintを渡すとエラーになること"""
        with pytest.raises(TradeIdValidationException):
            TradeId.create(0)
