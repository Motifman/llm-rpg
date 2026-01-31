from abc import abstractmethod
from typing import Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId


class TradeRepository(Repository[TradeAggregate, TradeId]):
    """取引リポジトリインターフェース"""

    @abstractmethod
    def generate_trade_id(self) -> TradeId:
        """新規取引IDを生成"""
        pass
