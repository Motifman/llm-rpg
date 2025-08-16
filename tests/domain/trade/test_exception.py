import pytest
from domain.trade.trade_exception import (
    TradeException,
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
    InsufficientItemsException,
    InsufficientGoldException,
)


class TestTradeExceptions:
    """取引関連例外クラスのテスト"""
    
    def test_trade_exception_inheritance(self):
        """例外の継承関係確認"""
        assert issubclass(InvalidTradeStatusException, TradeException)
        assert issubclass(CannotAcceptOwnTradeException, TradeException)
        assert issubclass(CannotAcceptTradeWithOtherPlayerException, TradeException)
        assert issubclass(CannotCancelTradeWithOtherPlayerException, TradeException)
        assert issubclass(InsufficientItemsException, TradeException)
        assert issubclass(InsufficientGoldException, TradeException)
    
    def test_invalid_trade_status_exception(self):
        """InvalidTradeStatusExceptionのテスト"""
        message = "Invalid status"
        exception = InvalidTradeStatusException(message)
        assert str(exception) == message
        assert isinstance(exception, TradeException)
    
    def test_cannot_accept_own_trade_exception(self):
        """CannotAcceptOwnTradeExceptionのテスト"""
        message = "Cannot accept own trade"
        exception = CannotAcceptOwnTradeException(message)
        assert str(exception) == message
        assert isinstance(exception, TradeException)
    
    def test_cannot_accept_trade_with_other_player_exception(self):
        """CannotAcceptTradeWithOtherPlayerExceptionのテスト"""
        message = "Cannot accept trade with other player"
        exception = CannotAcceptTradeWithOtherPlayerException(message)
        assert str(exception) == message
        assert isinstance(exception, TradeException)
    
    def test_cannot_cancel_trade_with_other_player_exception(self):
        """CannotCancelTradeWithOtherPlayerExceptionのテスト"""
        message = "Cannot cancel trade with other player"
        exception = CannotCancelTradeWithOtherPlayerException(message)
        assert str(exception) == message
        assert isinstance(exception, TradeException)
    
    def test_insufficient_items_exception(self):
        """InsufficientItemsExceptionのテスト"""
        message = "Insufficient items"
        exception = InsufficientItemsException(message)
        assert str(exception) == message
        assert isinstance(exception, TradeException)
    
    def test_insufficient_gold_exception(self):
        """InsufficientGoldExceptionのテスト"""
        message = "Insufficient gold"
        exception = InsufficientGoldException(message)
        assert str(exception) == message
        assert isinstance(exception, TradeException)
    
    def test_raise_exceptions(self):
        """例外の発生テスト"""
        with pytest.raises(InvalidTradeStatusException):
            raise InvalidTradeStatusException("test")
        
        with pytest.raises(CannotAcceptOwnTradeException):
            raise CannotAcceptOwnTradeException("test")
        
        with pytest.raises(CannotAcceptTradeWithOtherPlayerException):
            raise CannotAcceptTradeWithOtherPlayerException("test")
        
        with pytest.raises(CannotCancelTradeWithOtherPlayerException):
            raise CannotCancelTradeWithOtherPlayerException("test")
        
        with pytest.raises(InsufficientItemsException):
            raise InsufficientItemsException("test")
        
        with pytest.raises(InsufficientGoldException):
            raise InsufficientGoldException("test")

