"""
InMemoryRepositoryBase - インメモリリポジトリの基底クラス
Unit of Workとの統合ロジックを提供します。
"""
import copy
from typing import Optional, Callable, Any, TypeVar, Generic
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
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

    def _clone(self, obj: T) -> T:
        """オブジェクトを複製する（ロールバック支援のため）"""
        if obj is None:
            return None
        return copy.deepcopy(obj)

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

    def _register_aggregate(self, aggregate: Any) -> None:
        """集約をUOWに登録し、イベントの自動収集を有効にする"""
        if self._unit_of_work and self._is_in_transaction():
            if hasattr(self._unit_of_work, 'register_aggregate'):
                self._unit_of_work.register_aggregate(aggregate)

    def _repo_key(self) -> str:
        """同一トランザクション内の保留集約のキー用。リポジトリ種別の一意な文字列。"""
        return self.__class__.__name__

    def _register_pending_if_uow(self, entity_id: Any, aggregate: Any) -> None:
        """保存予定の集約をUoWに登録し、同一トランザクション内の find で未反映の状態を返せるようにする"""
        if self._unit_of_work and self._is_in_transaction():
            if hasattr(self._unit_of_work, 'register_pending_aggregate'):
                self._unit_of_work.register_pending_aggregate(self._repo_key(), entity_id, aggregate)

    def _get_pending_aggregate(self, entity_id: Any) -> Optional[Any]:
        """同一トランザクション内で保留中の集約があれば返す"""
        if not self._unit_of_work or not self._is_in_transaction():
            return None
        if hasattr(self._unit_of_work, 'get_pending_aggregate'):
            return self._unit_of_work.get_pending_aggregate(self._repo_key(), entity_id)
        return None

    def _is_in_transaction(self) -> bool:
        """トランザクション中かどうかを確認"""
        if not self._unit_of_work:
            return False
        
        # InMemoryUnitOfWorkのis_in_transactionメソッドを確認
        if hasattr(self._unit_of_work, 'is_in_transaction'):
            return self._unit_of_work.is_in_transaction()
        
        return False
