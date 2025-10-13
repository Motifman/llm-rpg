from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.domain.common.repository import Repository
from src.domain.trade.read_model.global_market_listing_read_model import GlobalMarketListingReadModel
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.item.enum.item_enum import ItemType, Rarity
from src.domain.trade.repository.cursor import ListingCursor


@dataclass(frozen=True)
class GlobalMarketFilter:
    """グローバル取引所フィルタ条件"""
    item_type: Optional[ItemType] = None
    item_rarity: Optional[Rarity] = None
    search_text: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None


class GlobalMarketListingReadModelRepository(Repository[GlobalMarketListingReadModel, TradeId]):
    """グローバル取引所ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_listings(
        self,
        filter_condition: GlobalMarketFilter,
        limit: int = 50,
        cursor: Optional[ListingCursor] = None
    ) -> Tuple[List[GlobalMarketListingReadModel], Optional[ListingCursor]]:
        """フィルタ条件で出品を取得（カーソルベースページング）

        Args:
            filter_condition: フィルタ条件
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (出品リスト, 次のページのカーソル)
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
