from abc import abstractmethod
from typing import Optional

from src.domain.common.repository import Repository
from src.domain.trade.read_model.recent_trade_read_model import RecentTradeReadModel
from src.domain.item.value_object.item_spec_id import ItemSpecId


class RecentTradeReadModelRepository(Repository[RecentTradeReadModel, ItemSpecId]):
    """アイテム別最近取引履歴ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_by_item_name(self, item_name: str) -> Optional[RecentTradeReadModel]:
        """アイテム名で最近の取引履歴を取得

        Args:
            item_name: アイテム名

        Returns:
            指定アイテムの最近取引履歴（存在しない場合はNone）
        """
        pass
