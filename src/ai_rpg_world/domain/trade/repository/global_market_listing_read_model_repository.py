from abc import abstractmethod
from typing import List, Optional, Tuple

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.trade.read_model.global_market_listing_read_model import GlobalMarketListingReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor


class GlobalMarketListingReadModelRepository(Repository[GlobalMarketListingReadModel, TradeId]):
    """グローバル取引所ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_listings(
        self,
        filter_condition: TradeSearchFilter,
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
    def count_listings(self, filter_condition: TradeSearchFilter) -> int:
        """フィルタ条件に一致する出品数をカウント

        Args:
            filter_condition: フィルタ条件

        Returns:
            出品数
        """
        pass
