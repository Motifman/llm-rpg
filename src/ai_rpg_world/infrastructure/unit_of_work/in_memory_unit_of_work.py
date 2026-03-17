"""
InMemoryUnitOfWork - インメモリ実装のUnit of Work
実際のデータベーストランザクションは存在しないが、論理的なトランザクション境界を提供します。
"""
import logging
from typing import List, Callable, Any, Tuple, TYPE_CHECKING, Optional, Dict

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow

logger = logging.getLogger(__name__)


class InMemoryUnitOfWork(UnitOfWork):
    """インメモリ実装のUnit of Work

    実際のDBトランザクションはないが、論理的なトランザクション境界を提供し、
    複数の集約更新の一貫性を保証します。
    """

    def __init__(self, event_publisher=None, unit_of_work_factory=None, data_store=None, sync_event_dispatcher=None):
        self._in_transaction = False
        self._pending_operations: List[Callable[[], None]] = []
        self._pending_events: List[BaseDomainEvent[Any, Any]] = []
        self._pending_aggregates: Dict[Tuple[str, Any], Any] = {}  # (repo_key, entity_id) -> 未反映の集約
        self._processed_sync_count = 0
        self._committed = False
        self._event_publisher = event_publisher
        self._data_store = data_store
        self._snapshot = None
        self._sync_event_dispatcher = sync_event_dispatcher

        # 別トランザクション処理専用 - 必須パラメータ
        if unit_of_work_factory is None:
            raise ValueError("unit_of_work_factory is required for separate transaction event processing")
        self._unit_of_work_factory = unit_of_work_factory

    @property
    def sync_event_dispatcher(self):
        """Phase 5.2: Coordinator 等に注入する SyncEventDispatcher を返す。create_with_event_publisher で生成された場合のみ存在。"""
        return self._sync_event_dispatcher

    def begin(self) -> None:
        """トランザクション開始"""
        if self._in_transaction:
            raise RuntimeError("Transaction already in progress")
        self._in_transaction = True
        self._pending_operations = []
        self._pending_events = []
        self._pending_aggregates = {}
        self._processed_sync_count = 0
        self._committed = False
        
        # ロールバック用にスナップショットを取得
        if self._data_store:
            self._snapshot = self._data_store.take_snapshot()

    def commit(self) -> None:
        """コミット - 保留中の操作を実行し、同一トランザクションで同期イベント、別トランザクションで非同期イベントを処理"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        try:
            # 1. 同期イベントの処理（保留中の操作も適宜実行される）
            # イベントは add_events 経由のみで pending_events に追加される（Phase 4）
            # create_with_event_publisher 経由で作成された場合のみ dispatcher が存在
            if self._sync_event_dispatcher:
                self._sync_event_dispatcher.flush_sync_events()

            # 2. 残った保留中の操作があれば実行
            self._execute_pending_operations()

            self._committed = True

        except Exception as e:
            # コミット失敗時はロールバック
            self.rollback()
            raise e
        finally:
            # トランザクション完了後は状態をクリアするが、
            # 非同期イベント処理のためにイベントリストは一時的に保持
            events_to_process_async = self._pending_events.copy()
            
            self._in_transaction = False
            self._pending_operations.clear()
            self._pending_events.clear()
            self._pending_aggregates = {}
            self._processed_sync_count = 0 # リセット
            self._snapshot = None

            # コミット成功時のみ、別トランザクションで非同期イベントを処理
            if self._committed and events_to_process_async:
                self._pending_events = events_to_process_async
                self._process_events_in_separate_transaction()
                self._pending_events.clear()

    def _execute_pending_operations(self) -> None:
        """保留中の操作を順次実行する"""
        while self._pending_operations:
            # 操作の実行中にさらに操作が追加される可能性があるため
            operations = self._pending_operations.copy()
            self._pending_operations.clear()
            for operation in operations:
                operation()

    def execute_pending_operations(self) -> None:
        """保留中の操作を順次実行する（SyncEventDispatcher から呼び出される）"""
        self._execute_pending_operations()

    def _process_events_in_separate_transaction(self) -> None:
        """保留中のイベントを別トランザクションで処理（非同期ハンドラ）

        非同期ハンドラは各ハンドラが自分で UoW を管理するため、
        外側の UoW は廃止し、publish_pending_events を直接呼ぶ。
        """
        if not self._pending_events:
            return

        # イベントパブリッシャーがない場合は処理をスキップ（テスト等で event_publisher=None のとき）
        if self._event_publisher is None:
            return

        try:
            self._event_publisher._pending_events.extend(self._pending_events)
            self._event_publisher.publish_pending_events()
        except Exception as e:
            logger.exception("Failed to process async events in separate transaction: %s", e)
            raise

    def rollback(self) -> None:
        """ロールバック - 保留中の操作を破棄し、状態を復元"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        # 状態を復元
        if self._data_store and self._snapshot:
            self._data_store.restore_snapshot(self._snapshot)

        # 保留中の操作をクリア
        self._pending_operations.clear()
        self._pending_events.clear()
        self._pending_aggregates = {}
        self._committed = False
        self._in_transaction = False
        self._snapshot = None

    def register_pending_aggregate(self, repo_key: str, entity_id: Any, aggregate: Any) -> None:
        """同一トランザクション内で find が未反映の集約を返せるよう、保留中の集約を登録する"""
        if not self._in_transaction:
            return
        self._pending_aggregates[(repo_key, entity_id)] = aggregate

    def get_pending_aggregate(self, repo_key: str, entity_id: Any) -> Optional[Any]:
        """保留中の集約があれば返す（同一トランザクション内の一貫した find 用）"""
        if not self._in_transaction:
            return None
        return self._pending_aggregates.get((repo_key, entity_id))

    def add_operation(self, operation: Callable[[], None]) -> None:
        """保留中の操作を追加"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_operations.append(operation)

    def add_events(self, events: List[BaseDomainEvent[Any, Any]]) -> None:
        """保留中のイベントを追加"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_events.extend(events)

    def add_events_from_aggregate(self, aggregate: Any) -> None:
        """集約からイベントを収集し、add_events 経由で追加する（イベント収集 1 本化）"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        if hasattr(aggregate, 'get_events') and hasattr(aggregate, 'clear_events'):
            events = aggregate.get_events()
            if events:
                self._pending_events.extend(events)
            aggregate.clear_events()

    def get_pending_events(self) -> List[BaseDomainEvent[Any, Any]]:
        """保留中のイベントを取得（テスト用）"""
        return self._pending_events.copy()

    def clear_pending_events(self) -> None:
        """保留中のイベントをクリア"""
        self._pending_events.clear()

    def is_in_transaction(self) -> bool:
        """トランザクション中かどうかを返す（テスト用）"""
        return self._in_transaction

    def get_sync_processed_count(self) -> int:
        """同期イベント処理済み件数を返す。"""
        return self._processed_sync_count

    def get_pending_events_since(self, processed_count: int) -> Tuple[List[BaseDomainEvent[Any, Any]], int]:
        """processed_count 以降の保留イベントを取得する。戻り値は (イベントリスト, 次の processed_count)。"""
        events = self._pending_events[processed_count:]
        return (events, len(self._pending_events))

    def advance_sync_processed_count(self, new_count: int) -> None:
        """同期イベント処理済み件数を進める。"""
        self._processed_sync_count = new_count

    def is_committed(self) -> bool:
        """コミット済みかどうかを返す（テスト用）"""
        return self._committed

    def __enter__(self):
        """コンテキストマネージャー開始"""
        self.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了"""
        if exc_type is not None:
            # 例外が発生したらロールバック
            self.rollback()
        else:
            # 正常終了したらコミット
            self.commit()

    @classmethod
    def create_with_event_publisher(cls, unit_of_work_factory=None, data_store=None) -> Tuple["InMemoryUnitOfWork", "InMemoryEventPublisherWithUow"]:
        """Unit of Workとイベントパブリッシャーを作成し、適切に接続する
        
        双方向参照の設定をカプセル化し、テストでの使用を簡素化します。

        Args:
            unit_of_work_factory: 別トランザクション用のUnit of Workファクトリ（必須）
            data_store: 状態復元用のデータストア

        Returns:
            (unit_of_work, event_publisher)のタプル
        """
        if unit_of_work_factory is None:
            raise ValueError("unit_of_work_factory is required for separate transaction event processing")

        # 実行時にインポートして循環インポートを回避
        from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow
        from ai_rpg_world.infrastructure.events.sync_event_dispatcher import SyncEventDispatcher

        unit_of_work = cls(unit_of_work_factory=unit_of_work_factory, data_store=data_store)
        event_publisher = InMemoryEventPublisherWithUow(unit_of_work)
        unit_of_work._event_publisher = event_publisher

        sync_event_dispatcher = SyncEventDispatcher(unit_of_work, event_publisher)
        unit_of_work._sync_event_dispatcher = sync_event_dispatcher

        return unit_of_work, event_publisher
