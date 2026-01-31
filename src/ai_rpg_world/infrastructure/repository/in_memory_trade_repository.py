"""
InMemoryTradeRepository - 取引関連のインメモリリポジトリ
"""
from typing import List, Optional, Dict, Any
from ai_rpg_world.domain.trade.repository.trade_repository import TradeRepository
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryTradeRepository(TradeRepository, InMemoryRepositoryBase):
    """取引リポジトリのインメモリ実装"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _trades(self) -> Dict[TradeId, TradeAggregate]:
        return self._data_store.trades

    def find_by_id(self, trade_id: TradeId) -> Optional[TradeAggregate]:
        return self._trades.get(trade_id)
    
    def find_by_ids(self, trade_ids: List[TradeId]) -> List[TradeAggregate]:
        return [self._trades[tid] for tid in trade_ids if tid in self._trades]
    
    def save(self, trade: TradeAggregate) -> TradeAggregate:
        def operation():
            self._trades[trade.trade_id] = trade
            return trade
            
        return self._execute_operation(operation)
    
    def delete(self, trade_id: TradeId) -> bool:
        def operation():
            if trade_id in self._trades:
                del self._trades[trade_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> List[TradeAggregate]:
        return list(self._trades.values())
    
    def generate_trade_id(self) -> TradeId:
        trade_id = self._data_store.next_trade_id
        self._data_store.next_trade_id += 1
        return TradeId(trade_id)
