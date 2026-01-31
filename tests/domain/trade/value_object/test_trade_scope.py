import pytest
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.trade.enum.trade_enum import TradeType
from ai_rpg_world.domain.trade.exception.trade_exception import TradeScopeValidationException


class TestTradeScope:
    """TradeScope値オブジェクトのテスト"""

    # ===== 正常系のテスト =====

    def test_create_global_trade(self):
        """グローバル取引を作成できること"""
        scope = TradeScope(TradeType.GLOBAL, None)
        assert scope.trade_type == TradeType.GLOBAL
        assert scope.target_player_id is None

    def test_create_direct_trade_with_player_id(self):
        """ダイレクト取引をプレイヤーID付きで作成できること"""
        player_id = PlayerId(123)
        scope = TradeScope(TradeType.DIRECT, player_id)
        assert scope.trade_type == TradeType.DIRECT
        assert scope.target_player_id == player_id

    def test_global_trade_factory_method(self):
        """global_tradeファクトリメソッドでグローバル取引を作成できること"""
        scope = TradeScope.global_trade()
        assert scope.trade_type == TradeType.GLOBAL
        assert scope.target_player_id is None
        assert isinstance(scope, TradeScope)

    def test_direct_trade_factory_method(self):
        """direct_tradeファクトリメソッドでダイレクト取引を作成できること"""
        player_id = PlayerId(456)
        scope = TradeScope.direct_trade(player_id)
        assert scope.trade_type == TradeType.DIRECT
        assert scope.target_player_id == player_id
        assert isinstance(scope, TradeScope)

    # ===== 異常系のテスト =====

    def test_create_direct_trade_without_player_id_raises_error(self):
        """ダイレクト取引でtarget_player_idがNoneの場合エラーになること"""
        with pytest.raises(TradeScopeValidationException):
            TradeScope(TradeType.DIRECT, None)

    def test_create_global_trade_with_player_id_raises_error(self):
        """グローバル取引でtarget_player_idが指定されている場合エラーになること"""
        player_id = PlayerId(789)
        with pytest.raises(TradeScopeValidationException):
            TradeScope(TradeType.GLOBAL, player_id)

    # ===== ヘルパーメソッドのテスト =====

    def test_is_global_returns_true_for_global_trade(self):
        """グローバル取引でis_globalがTrueを返すこと"""
        scope = TradeScope.global_trade()
        assert scope.is_global() is True
        assert scope.is_direct() is False

    def test_is_direct_returns_true_for_direct_trade(self):
        """ダイレクト取引でis_directがTrueを返すこと"""
        player_id = PlayerId(111)
        scope = TradeScope.direct_trade(player_id)
        assert scope.is_direct() is True
        assert scope.is_global() is False

    # ===== 文字列変換メソッドのテスト =====

    def test_str_representation_global_trade(self):
        """グローバル取引の__str__表現"""
        scope = TradeScope.global_trade()
        assert str(scope) == "グローバル取引"

    def test_str_representation_direct_trade(self):
        """ダイレクト取引の__str__表現"""
        player_id = PlayerId(222)
        scope = TradeScope.direct_trade(player_id)
        assert str(scope) == f"ダイレクト取引(対象: {player_id})"

    def test_repr_representation_global_trade(self):
        """グローバル取引の__repr__表現"""
        scope = TradeScope.global_trade()
        assert repr(scope) == f"TradeScope(trade_type={TradeType.GLOBAL.value}, target_player_id=None)"

    def test_repr_representation_direct_trade(self):
        """ダイレクト取引の__repr__表現"""
        player_id = PlayerId(333)
        scope = TradeScope.direct_trade(player_id)
        expected = f"TradeScope(trade_type={TradeType.DIRECT.value}, target_player_id={player_id})"
        assert repr(scope) == expected

    # ===== 等価性のテスト =====

    def test_equality_with_same_global_trade(self):
        """同じグローバル取引オブジェクトが等しいこと"""
        scope1 = TradeScope.global_trade()
        scope2 = TradeScope.global_trade()
        assert scope1 == scope2

    def test_equality_with_same_direct_trade(self):
        """同じダイレクト取引オブジェクトが等しいこと"""
        player_id = PlayerId(444)
        scope1 = TradeScope.direct_trade(player_id)
        scope2 = TradeScope.direct_trade(player_id)
        assert scope1 == scope2

    def test_equality_with_different_trade_types(self):
        """異なる取引タイプのオブジェクトが等しくないこと"""
        scope1 = TradeScope.global_trade()
        player_id = PlayerId(555)
        scope2 = TradeScope.direct_trade(player_id)
        assert scope1 != scope2

    def test_equality_with_different_player_ids(self):
        """異なるプレイヤーIDのダイレクト取引が等しくないこと"""
        player_id1 = PlayerId(666)
        player_id2 = PlayerId(777)
        scope1 = TradeScope.direct_trade(player_id1)
        scope2 = TradeScope.direct_trade(player_id2)
        assert scope1 != scope2


    # ===== 不変性のテスト =====

    def test_immutability(self):
        """オブジェクトが不変であること"""
        scope = TradeScope.global_trade()
        with pytest.raises(AttributeError):
            scope.trade_type = TradeType.DIRECT  # frozen=Trueなので変更不可

        with pytest.raises(AttributeError):
            scope.target_player_id = PlayerId(999)  # frozen=Trueなので変更不可
