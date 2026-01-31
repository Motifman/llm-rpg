"""
InMemoryRepositoryBase - インメモリリポジトリの基底クラス
Unit of Workとの統合ロジックを提供します。
"""
from typing import Optional, Callable, Any, TypeVar, Generic
from src.domain.common.unit_of_work import UnitOfWork
from .in_memory_data_store import InMemoryDataStore

T = TypeVar('T')

class InMemoryRepositoryBase:
    """インメモリリポジトリの共通基底クラス"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        """初期化
        
        Args:
            data_store: 共有データストア
            unit_of_work: Unit of Work (任意)
        """
        if data_store is None:
            data_store = InMemoryDataStore()
            
        self._data_store = data_store
        self._unit_of_work = unit_of_work

    def _execute_operation(self, operation: Callable[[], Any]) -> Any:
        """操作を実行またはUOWに登録
        
        Args:
            operation: 実行する操作
            
        Returns:
            操作が即時実行された場合はその戻り値、UOWに登録された場合はNone
        """
        if self._unit_of_work and self._is_in_transaction():
            # TODO: InMemoryUnitOfWorkに直接依存せずにProtocolで解決したいが
            # 現状はInMemoryUnitOfWorkのadd_operationメソッドが必要
            if hasattr(self._unit_of_work, 'add_operation'):
                self._unit_of_work.add_operation(operation)
                return None
            
        # トランザクション外、またはUOWが指定されていない場合は即時実行
        return operation()

    def _is_in_transaction(self) -> bool:
        """トランザクション中かどうかを確認"""
        if not self._unit_of_work:
            return False
        
        # InMemoryUnitOfWorkのis_in_transactionメソッドを確認
        if hasattr(self._unit_of_work, 'is_in_transaction'):
            return self._unit_of_work.is_in_transaction()
        
        return False
