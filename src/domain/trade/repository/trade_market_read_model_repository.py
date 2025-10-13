from abc import abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from src.domain.common.repository import Repository
from src.domain.trade.read_model.trade_market_read_model import TradeMarketReadModel
from src.domain.item.value_object.item_spec_id import ItemSpecId


class TradeMarketReadModelRepository(Repository[TradeMarketReadModel, ItemSpecId]):
    """取引相場・統計情報リポジトリインターフェース"""

    @abstractmethod
    def find_by_item_name(self, item_name: str) -> Optional[TradeMarketReadModel]:
        """アイテム名で市場情報を検索

        Args:
            item_name: アイテム名

        Returns:
            アイテムの市場情報（存在しない場合はNone）
        """
        pass

    @abstractmethod
    def find_popular_items(self, limit: int = 10) -> List[TradeMarketReadModel]:
        """人気アイテムの市場情報を取得（取引量順）

        Args:
            limit: 取得する最大件数

        Returns:
            人気アイテムの市場情報リスト（取引量の降順）
        """
        pass

