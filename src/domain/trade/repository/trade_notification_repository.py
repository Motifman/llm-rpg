from abc import abstractmethod
from typing import Optional, List
from src.domain.common.repository import Repository
from src.domain.trade.trade_notification import TradeNotification


class TradeNotificationRepository(Repository[TradeNotification]):
    """取引通知リポジトリインターフェース"""
    
    @abstractmethod
    def find_by_trade_id(self, trade_id: int) -> Optional[TradeNotification]:
        """取引IDで通知を検索"""
        pass
    
    @abstractmethod
    def find_by_trade_id_and_read(self, trade_id: int, read: bool) -> List[TradeNotification]:
        """取引IDと既読フラグで通知を検索"""
        pass
    
    @abstractmethod
    def generate_trade_notification_id(self) -> int:
        """取引通知IDを生成"""
        pass