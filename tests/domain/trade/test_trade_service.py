import pytest
from unittest.mock import Mock
from datetime import datetime
from src.domain.trade.trade_service import TradeService
from src.domain.trade.trade import TradeOffer, TradeItem
from src.domain.trade.trade_enum import TradeType, TradeStatus
from src.domain.trade.trade_exception import (
    InsufficientItemsException,
    InsufficientGoldException,
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
)


class TestTradeService:
    """TradeServiceクラスのテスト"""
    
    @pytest.fixture
    def trade_service(self):
        """TradeServiceインスタンス"""
        return TradeService()
    
    @pytest.fixture
    def sample_datetime(self):
        return datetime(2023, 1, 1, 12, 0, 0)
    
    @pytest.fixture
    def mock_seller(self):
        """モックの売り手プレイヤー"""
        mock_player = Mock()
        mock_player.player_id = 100
        mock_player.can_offer_item.return_value = True
        return mock_player
    
    @pytest.fixture
    def mock_buyer(self):
        """モックの買い手プレイヤー"""
        mock_player = Mock()
        mock_player.player_id = 200
        mock_player.can_pay_gold.return_value = True
        return mock_player
    
    @pytest.fixture
    def sample_trade_offer(self, sample_datetime):
        """サンプルの取引オファー"""
        return TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
    
    def test_execute_trade_success(self, trade_service, sample_trade_offer, mock_seller, mock_buyer):
        """正常な取引実行"""
        result = trade_service.execute_trade(sample_trade_offer, mock_buyer, mock_seller)
        
        assert result is True
        assert sample_trade_offer.status == TradeStatus.COMPLETED
        assert sample_trade_offer.buyer_id == 200
        
        # メソッド呼び出しの確認
        mock_seller.can_offer_item.assert_called_once_with(sample_trade_offer.offered_item)
        mock_buyer.can_pay_gold.assert_called_once_with(500)
        mock_seller.transfer_item_to.assert_called_once_with(mock_buyer, sample_trade_offer.offered_item)
        mock_buyer.transfer_gold_to.assert_called_once_with(mock_seller, 500)
    
    def test_execute_trade_insufficient_items(self, trade_service, sample_trade_offer, mock_seller, mock_buyer):
        """売り手のアイテム不足エラー"""
        mock_seller.can_offer_item.return_value = False
        
        with pytest.raises(InsufficientItemsException):
            trade_service.execute_trade(sample_trade_offer, mock_buyer, mock_seller)
        
        # 取引状態が変更されていないことを確認
        assert sample_trade_offer.status == TradeStatus.ACTIVE
        assert sample_trade_offer.buyer_id is None
    
    def test_execute_trade_insufficient_gold(self, trade_service, sample_trade_offer, mock_seller, mock_buyer):
        """買い手の所持金不足エラー"""
        mock_buyer.can_pay_gold.return_value = False
        
        with pytest.raises(InsufficientGoldException):
            trade_service.execute_trade(sample_trade_offer, mock_buyer, mock_seller)
        
        # 取引状態が変更されていないことを確認
        assert sample_trade_offer.status == TradeStatus.ACTIVE
        assert sample_trade_offer.buyer_id is None
    
    def test_execute_trade_own_trade_error(self, trade_service, sample_trade_offer, mock_seller):
        """自分の取引を受託するエラー"""
        # 同じプレイヤーを売り手と買い手にする
        mock_seller.player_id = 100
        mock_buyer_same_as_seller = Mock()
        mock_buyer_same_as_seller.player_id = 100
        
        with pytest.raises(CannotAcceptOwnTradeException):
            trade_service.execute_trade(sample_trade_offer, mock_buyer_same_as_seller, mock_seller)
    
    def test_execute_trade_invalid_status(self, trade_service, sample_trade_offer, mock_seller, mock_buyer):
        """非アクティブ状態での取引実行エラー"""
        sample_trade_offer.status = TradeStatus.COMPLETED
        
        with pytest.raises(InvalidTradeStatusException):
            trade_service.execute_trade(sample_trade_offer, mock_buyer, mock_seller)
    
    def test_cancel_trade(self, trade_service, sample_trade_offer, mock_seller):
        """取引キャンセル"""
        trade_service.cancel_trade(sample_trade_offer, mock_seller)
        
        assert sample_trade_offer.status == TradeStatus.CANCELLED
    
    def test_cancel_trade_wrong_player(self, trade_service, sample_trade_offer, mock_buyer):
        """他人による取引キャンセルエラー"""
        with pytest.raises(Exception):  # CannotCancelTradeWithOtherPlayerException
            trade_service.cancel_trade(sample_trade_offer, mock_buyer)
    
    def test_execute_trade_with_unique_item(self, trade_service, mock_seller, mock_buyer, sample_datetime):
        """固有アイテムでの取引実行"""
        unique_trade = TradeOffer.create_trade(
            trade_id=2,
            seller_id=100,
            requested_gold=1000,
            offered_item_id=2,
            offered_unique_id=100,
            created_at=sample_datetime
        )
        
        result = trade_service.execute_trade(unique_trade, mock_buyer, mock_seller)
        
        assert result is True
        assert unique_trade.status == TradeStatus.COMPLETED
        assert unique_trade.buyer_id == 200
        
        # 固有アイテムの確認
        assert unique_trade.offered_item.unique_id == 100
        assert unique_trade.offered_item.count is None
    
    def test_execute_trade_direct_trade(self, trade_service, mock_seller, mock_buyer, sample_datetime):
        """直接取引の実行"""
        direct_trade = TradeOffer.create_trade(
            trade_id=3,
            seller_id=100,
            requested_gold=750,
            offered_item_id=3,
            offered_item_count=10,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=200
        )
        
        result = trade_service.execute_trade(direct_trade, mock_buyer, mock_seller)
        
        assert result is True
        assert direct_trade.status == TradeStatus.COMPLETED
        assert direct_trade.buyer_id == 200
        assert direct_trade.is_direct_trade() is True

