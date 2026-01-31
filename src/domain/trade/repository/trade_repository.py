from abc import abstractmethod
from typing import Optional
from src.domain.common.repository import Repository
from src.domain.trade.aggregate.trade_aggregate import TradeAggregate
from src.domain.trade.value_object.trade_id import TradeId


class TradeRepository(Repository[TradeAggregate, TradeId]):
    """取引リポジトリインターフェース"""

    @abstractmethod
    def generate_trade_id(self) -> TradeId:
        """新規取引IDを生成"""
        pass
