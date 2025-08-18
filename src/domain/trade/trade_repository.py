from abc import abstractmethod
from typing import Optional, List
from src.domain.common.repository import Repository
from src.domain.trade.trade import TradeOffer
from src.domain.trade.trade_enum import TradeType, TradeStatus


class TradeRepository(Repository[TradeOffer]):
    """取引リポジトリインターフェース"""
    
    @abstractmethod
    def find_by_seller_id(self, seller_id: int) -> List[TradeOffer]:
        """売り手IDで取引を検索"""
        pass
    
    @abstractmethod
    def find_by_buyer_id(self, buyer_id: int) -> List[TradeOffer]:
        """買い手IDで取引を検索"""
        pass
    
    @abstractmethod
    def find_by_target_player_id(self, target_player_id: int) -> List[TradeOffer]:
        """対象プレイヤーIDで取引を検索"""
        pass
    
    @abstractmethod
    def find_active_trades(self) -> List[TradeOffer]:
        """アクティブな取引を全て取得"""
        pass
    
    @abstractmethod
    def find_global_trades(self) -> List[TradeOffer]:
        """グローバル取引を全て取得"""
        pass
    
    @abstractmethod
    def find_by_item_id(self, item_id: int) -> List[TradeOffer]:
        """アイテムIDで取引を検索"""
        pass
    
    @abstractmethod
    def find_by_price_range(self, min_price: int, max_price: int) -> List[TradeOffer]:
        """価格範囲で取引を検索"""
        pass
    
    @abstractmethod
    def find_recent_trades(self, limit: int = 10) -> List[TradeOffer]:
        """最新の取引を取得"""
        pass
    
    @abstractmethod
    def generate_trade_id(self) -> int:
        """取引IDを生成"""
        pass
