from abc import abstractmethod
from typing import Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.trade.read_model.item_trade_statistics_read_model import ItemTradeStatisticsReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


class ItemTradeStatisticsReadModelRepository(Repository[ItemTradeStatisticsReadModel, ItemSpecId]):
    """アイテム取引統計ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_statistics(self, item_spec_id: ItemSpecId) -> Optional[ItemTradeStatisticsReadModel]:
        """アイテムスペックIDで統計情報を取得

        Args:
            item_spec_id: アイテムスペックID

        Returns:
            統計情報（存在しない場合はNone）
        """
        pass
