from abc import abstractmethod

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.item_trade_statistics_read_model import ItemTradeStatisticsReadModel


class ItemTradeStatisticsReadModelRepository(Repository[ItemTradeStatisticsReadModel, ItemSpecId]):
    """アイテム取引統計ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_statistics(self, item_spec_id: ItemSpecId) -> ItemTradeStatisticsReadModel | None:
        """アイテムスペックIDで統計情報を取得

        Args:
            item_spec_id: アイテムスペックID

        Returns:
            統計情報（存在しない場合はNone）
        """
        pass
