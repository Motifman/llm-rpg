import pytest
from src.domain.trade.trade_enum import TradeType, TradeStatus


class TestTradeType:
    """TradeTypeクラスのテスト"""
    
    def test_trade_type_values(self):
        """TradeTypeの値確認"""
        assert TradeType.GLOBAL.value == "global"
        assert TradeType.DIRECT.value == "direct"
    
    def test_trade_type_members(self):
        """TradeTypeのメンバー確認"""
        assert len(TradeType) == 2
        assert TradeType.GLOBAL in TradeType
        assert TradeType.DIRECT in TradeType


class TestTradeStatus:
    """TradeStatusクラスのテスト"""
    
    def test_trade_status_values(self):
        """TradeStatusの値確認"""
        assert TradeStatus.ACTIVE.value == "active"
        assert TradeStatus.COMPLETED.value == "completed"
        assert TradeStatus.CANCELLED.value == "cancelled"
    
    def test_trade_status_members(self):
        """TradeStatusのメンバー確認"""
        assert len(TradeStatus) == 3
        assert TradeStatus.ACTIVE in TradeStatus
        assert TradeStatus.COMPLETED in TradeStatus
        assert TradeStatus.CANCELLED in TradeStatus

