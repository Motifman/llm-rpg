from abc import abstractmethod
from typing import Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.trade.read_model.trade_detail_read_model import TradeDetailReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId


class TradeDetailReadModelRepository(Repository[TradeDetailReadModel, TradeId]):
    """取引詳細ReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_detail(self, trade_id: TradeId) -> Optional[TradeDetailReadModel]:
        """取引IDで詳細情報を取得

        Args:
            trade_id: 取引ID

        Returns:
            取引詳細情報（存在しない場合はNone）
        """
        pass
