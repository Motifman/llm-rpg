import pytest
from datetime import datetime
from src.domain.trade.trade import TradeItem, TradeOffer
from domain.trade.trade_enum import TradeType, TradeStatus
from domain.trade.trade_exception import (
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
)


class TestTradeItem:
    """TradeItemクラスのテスト"""
    
    def test_stackable_item_creation(self):
        """スタック可能アイテムの作成"""
        item = TradeItem.stackable(item_id=1, count=5)
        assert item.item_id == 1
        assert item.count == 5
        assert item.unique_id is None
    
    def test_unique_item_creation(self):
        """固有アイテムの作成"""
        item = TradeItem.unique(item_id=2, unique_id=100)
        assert item.item_id == 2
        assert item.unique_id == 100
        assert item.count is None
    
    def test_invalid_item_creation_no_count_or_unique_id(self):
        """countもunique_idも無い場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeItem(item_id=1)
    
    def test_invalid_item_creation_both_count_and_unique_id(self):
        """countとunique_idの両方がある場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeItem(item_id=1, count=5, unique_id=100)
    
    def test_invalid_item_creation_zero_count(self):
        """countが0以下の場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeItem.stackable(item_id=1, count=0)
    
    def test_invalid_item_creation_negative_count(self):
        """countが負の場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeItem.stackable(item_id=1, count=-1)


class TestTradeOffer:
    """TradeOfferクラスのテスト"""
    
    @pytest.fixture
    def sample_datetime(self):
        return datetime(2023, 1, 1, 12, 0, 0)
    
    def test_create_stackable_trade_offer(self, sample_datetime):
        """スタック可能アイテムの取引オファー作成"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        assert trade.trade_id == 1
        assert trade.seller_id == 100
        assert trade.requested_gold == 500
        assert trade.offered_item.item_id == 1
        assert trade.offered_item.count == 5
        assert trade.offered_item.unique_id is None
        assert trade.status == TradeStatus.ACTIVE
        assert trade.trade_type == TradeType.GLOBAL
        assert trade.buyer_id is None
    
    def test_create_unique_trade_offer(self, sample_datetime):
        """固有アイテムの取引オファー作成"""
        trade = TradeOffer.create_trade(
            trade_id=2,
            seller_id=200,
            requested_gold=1000,
            offered_item_id=2,
            offered_unique_id=100,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=300
        )
        
        assert trade.trade_id == 2
        assert trade.seller_id == 200
        assert trade.requested_gold == 1000
        assert trade.offered_item.item_id == 2
        assert trade.offered_item.unique_id == 100
        assert trade.offered_item.count is None
        assert trade.trade_type == TradeType.DIRECT
        assert trade.target_player_id == 300
    
    def test_invalid_trade_offer_creation_none_trade_id(self, sample_datetime):
        """trade_idがNoneの場合のエラー"""
        with pytest.raises(ValueError, match="trade_id cannot be None"):
            TradeOffer(
                trade_id=None,
                seller_id=100,
                offered_item=TradeItem.stackable(1, 5),
                requested_gold=500,
                created_at=sample_datetime
            )
    
    def test_invalid_trade_offer_creation_none_seller_id(self, sample_datetime):
        """seller_idがNoneの場合のエラー"""
        with pytest.raises(ValueError, match="seller_id cannot be None"):
            TradeOffer(
                trade_id=1,
                seller_id=None,
                offered_item=TradeItem.stackable(1, 5),
                requested_gold=500,
                created_at=sample_datetime
            )
    
    def test_invalid_trade_offer_creation_completed_status(self, sample_datetime):
        """COMPLETED状態で初期化する場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeOffer(
                trade_id=1,
                seller_id=100,
                offered_item=TradeItem.stackable(1, 5),
                requested_gold=500,
                created_at=sample_datetime,
                status=TradeStatus.COMPLETED
            )
    
    def test_invalid_trade_offer_creation_with_buyer_id(self, sample_datetime):
        """buyer_idが設定された状態で初期化する場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeOffer(
                trade_id=1,
                seller_id=100,
                offered_item=TradeItem.stackable(1, 5),
                requested_gold=500,
                created_at=sample_datetime,
                buyer_id=200
            )
    
    def test_invalid_trade_offer_creation_target_player_without_direct_type(self, sample_datetime):
        """DIRECT以外でtarget_player_idが設定された場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeOffer(
                trade_id=1,
                seller_id=100,
                offered_item=TradeItem.stackable(1, 5),
                requested_gold=500,
                created_at=sample_datetime,
                trade_type=TradeType.GLOBAL,
                target_player_id=200
            )
    
    def test_invalid_trade_offer_creation_zero_gold(self, sample_datetime):
        """requested_goldが0以下の場合のエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeOffer(
                trade_id=1,
                seller_id=100,
                offered_item=TradeItem.stackable(1, 5),
                requested_gold=0,
                created_at=sample_datetime
            )
    
    def test_is_active(self, sample_datetime):
        """アクティブ状態の確認"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        assert trade.is_active() is True
        
        trade.status = TradeStatus.COMPLETED
        assert trade.is_active() is False
    
    def test_is_direct_trade(self, sample_datetime):
        """直接取引の確認"""
        global_trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime,
            trade_type=TradeType.GLOBAL
        )
        assert global_trade.is_direct_trade() is False
        
        direct_trade = TradeOffer.create_trade(
            trade_id=2,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=200
        )
        assert direct_trade.is_direct_trade() is True
    
    def test_is_for_player(self, sample_datetime):
        """特定プレイヤー向け取引の確認"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=200
        )
        
        assert trade.is_for_player(200) is True
        assert trade.is_for_player(300) is False
    
    def test_can_be_accepted_by(self, sample_datetime):
        """受託可能性の確認"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        # 正常ケース
        assert trade.can_be_accepted_by(200) is True
        
        # 自分の出品は受託できない
        assert trade.can_be_accepted_by(100) is False
        
        # 非アクティブ状態では受託できない
        trade.status = TradeStatus.COMPLETED
        assert trade.can_be_accepted_by(200) is False
    
    def test_can_be_accepted_by_direct_trade(self, sample_datetime):
        """直接取引の受託可能性確認"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=200
        )
        
        # 対象プレイヤーは受託可能
        assert trade.can_be_accepted_by(200) is True
        
        # 対象外プレイヤーは受託不可
        assert trade.can_be_accepted_by(300) is False
    
    def test_accept_by(self, sample_datetime):
        """取引受託"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        trade.accept_by(200)
        
        assert trade.buyer_id == 200
        assert trade.status == TradeStatus.COMPLETED
    
    def test_accept_by_invalid_status(self, sample_datetime):
        """非アクティブ状態での受託エラー"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        trade.status = TradeStatus.COMPLETED
        
        with pytest.raises(InvalidTradeStatusException):
            trade.accept_by(200)
    
    def test_accept_by_own_trade(self, sample_datetime):
        """自分の取引を受託するエラー"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        with pytest.raises(CannotAcceptOwnTradeException):
            trade.accept_by(100)
    
    def test_accept_by_direct_trade_wrong_player(self, sample_datetime):
        """直接取引で対象外プレイヤーが受託するエラー"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=200
        )
        
        with pytest.raises(CannotAcceptTradeWithOtherPlayerException, match="Cannot accept trade with other player"):
            trade.accept_by(300)
    
    def test_cancel_by(self, sample_datetime):
        """取引キャンセル"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        trade.cancel_by(100)
        
        assert trade.status == TradeStatus.CANCELLED
    
    def test_cancel_by_invalid_status(self, sample_datetime):
        """非アクティブ状態でのキャンセルエラー"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        trade.status = TradeStatus.COMPLETED
        
        with pytest.raises(InvalidTradeStatusException):
            trade.cancel_by(100)
    
    def test_cancel_by_wrong_player(self, sample_datetime):
        """他人の取引をキャンセルするエラー"""
        trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        with pytest.raises(CannotCancelTradeWithOtherPlayerException):
            trade.cancel_by(200)
    
    def test_get_trade_summary(self, sample_datetime):
        """取引サマリーの取得"""
        stackable_trade = TradeOffer.create_trade(
            trade_id=1,
            seller_id=100,
            requested_gold=500,
            offered_item_id=1,
            offered_item_count=5,
            created_at=sample_datetime
        )
        
        summary = stackable_trade.get_trade_summary()
        assert "1 x5" in summary
        assert "500 G" in summary
        assert "グローバル取引" in summary
        
        unique_trade = TradeOffer.create_trade(
            trade_id=2,
            seller_id=100,
            requested_gold=1000,
            offered_item_id=2,
            offered_unique_id=100,
            created_at=sample_datetime,
            trade_type=TradeType.DIRECT,
            target_player_id=200
        )
        
        summary = unique_trade.get_trade_summary()
        assert "2 x" in summary
        assert "(固有ID:100)" in summary
        assert "1000 G" in summary
        assert "直接取引" in summary
    
    def test_create_trade_without_item_specifications(self, sample_datetime):
        """アイテム情報不足でのエラー"""
        with pytest.raises(InvalidTradeStatusException):
            TradeOffer.create_trade(
                trade_id=1,
                seller_id=100,
                requested_gold=500,
                offered_item_id=1,
                created_at=sample_datetime
            )

