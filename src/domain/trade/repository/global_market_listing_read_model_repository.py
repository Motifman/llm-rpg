from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from src.domain.common.repository import Repository
from src.domain.trade.read_model.global_market_listing_read_model import GlobalMarketListingReadModel
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.item.enum.item_enum import ItemType, Rarity


@dataclass(frozen=True)
class GlobalMarketFilter:
    """グローバル取引所フィルタ条件"""
    item_type: Optional[ItemType] = None
    item_rarity: Optional[Rarity] = None
    search_text: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None


@dataclass(frozen=True)
class PageSpec:
    """ページング仕様"""
    limit: int
    offset: Optional[int] = None  # cursor-basedの場合はNone


class GlobalMarketListingReadModelRepository(Repository[GlobalMarketListingReadModel, TradeId]):
    """グローバル取引所ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_listings(
        self,
        filter_condition: GlobalMarketFilter,
        page_spec: PageSpec
    ) -> tuple[List[GlobalMarketListingReadModel], bool]:
        """フィルタ条件で出品を取得（ページング）

        Args:
            filter_condition: フィルタ条件
            page_spec: ページング仕様

        Returns:
            (出品リスト, 次のページが存在するか)
        """
        pass

    @abstractmethod
    def count_listings(self, filter_condition: GlobalMarketFilter) -> int:
        """フィルタ条件に一致する出品数をカウント

        Args:
            filter_condition: フィルタ条件

        Returns:
            出品数
        """
        pass
