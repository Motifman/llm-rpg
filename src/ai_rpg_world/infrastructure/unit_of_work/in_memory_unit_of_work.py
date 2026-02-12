"""
InMemoryUnitOfWork - インメモリ実装のUnit of Work
実際のデータベーストランザクションは存在しないが、論理的なトランザクション境界を提供します。
"""
from typing import List, Callable, Any, Tuple, TYPE_CHECKING, Optional
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.domain_event import DomainEvent

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class InMemoryUnitOfWork(UnitOfWork):
    """インメモリ実装のUnit of Work

    実際のDBトランザクションはないが、論理的なトランザクション境界を提供し、
    複数の集約更新の一貫性を保証します。
    """

    def __init__(self, event_publisher=None, unit_of_work_factory=None, data_store=None):
        self._in_transaction = False
        self._pending_operations: List[Callable[[], None]] = []
        self._pending_events: List[DomainEvent] = []
        self._registered_aggregates: set = set()
        self._processed_sync_count = 0
        self._committed = False
        self._event_publisher = event_publisher
        self._data_store = data_store
        self._snapshot = None

        # 別トランザクション処理専用 - 必須パラメータ
        if unit_of_work_factory is None:
            raise ValueError("unit_of_work_factory is required for separate transaction event processing")
        self._unit_of_work_factory = unit_of_work_factory

    def begin(self) -> None:
        """トランザクション開始"""
        if self._in_transaction:
            raise RuntimeError("Transaction already in progress")
        self._in_transaction = True
        self._pending_operations = []
        self._pending_events = []
        self._registered_aggregates = set()
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
            # 1. 登録された集約から最終的なイベントを収集
            self._collect_events_from_aggregates()

            # 2. 同期イベントの処理（保留中の操作も適宜実行される）
            self.process_sync_events()

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

    def process_sync_events(self) -> None:
        """同期イベントを即座に処理する（同一トランザクション内）"""
        if not self._in_transaction:
            return

        if not hasattr(self, '_processed_sync_count'):
            self._processed_sync_count = 0

        while True:
            # 処理前に、現時点で登録されている集約からイベントを収集
            self._collect_events_from_aggregates()
            
            # 同期イベントを処理する前に、そこまでの操作を全て反映させる
            # これにより、ハンドラが最新の状態をリポジトリから取得できる
            self._execute_pending_operations()
            
            if self._processed_sync_count >= len(self._pending_events):
                break
                
            events_to_process = self._pending_events[self._processed_sync_count:]
            self._processed_sync_count = len(self._pending_events)
            if self._event_publisher:
                self._event_publisher.publish_sync_events(events_to_process)

    def _process_events_in_separate_transaction(self) -> None:
        """保留中のイベントを別トランザクションで処理（非同期ハンドラ）"""
        if not self._pending_events:
            return

        # 別トランザクションを開始
        separate_uow = self._unit_of_work_factory()
        try:
            with separate_uow:
                # メインのイベントパブリッシャーを使用してイベントを発行
                if self._event_publisher is not None:
                    # 保留中のイベントを別トランザクションのパブリッシャーに渡す
                    separate_uow._event_publisher = self._event_publisher
                    separate_uow._event_publisher._pending_events.extend(self._pending_events)
                    separate_uow._event_publisher.publish_pending_events()
                else:
                    # イベントパブリッシャーがない場合でも、メインのイベントパブリッシャーのハンドラーを使用
                    for event in self._pending_events:
                        event_type = type(event)
                        # 非同期ハンドラーを使用
                        handlers = self._event_publisher._async_handlers.get(event_type, [])
                        for handler in handlers:
                            try:
                                handler.handle(event)
                            except Exception as e:
                                # イベント処理の失敗はメインのビジネスロジックに影響を与えない
                                print(f"Error handling event {event_type} in separate transaction: {e}")

        except Exception as e:
            # イベント処理全体の失敗はログに記録するが、メインのコミットを失敗させない
            print(f"Failed to process events in separate transaction: {e}")

    def rollback(self) -> None:
        """ロールバック - 保留中の操作を破棄し、状態を復元"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        # 集約の状態を戻すことはできない（メモリ上のオブジェクトが直接変更されているため）が、
        # 登録情報はクリアする
        self._registered_aggregates.clear()

        # 状態を復元
        if self._data_store and self._snapshot:
            self._data_store.restore_snapshot(self._snapshot)

        # 保留中の操作をクリア
        self._pending_operations.clear()
        self._pending_events.clear()
        self._committed = False
        self._in_transaction = False
        self._snapshot = None

    def add_operation(self, operation: Callable[[], None]) -> None:
        """保留中の操作を追加"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_operations.append(operation)

    def add_events(self, events: List[DomainEvent]) -> None:
        """保留中のイベントを追加"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_events.extend(events)

    def register_aggregate(self, aggregate: Any) -> None:
        """集約を登録し、コミット時にイベントを自動収集できるようにする"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._registered_aggregates.add(aggregate)

    def _collect_events_from_aggregates(self) -> None:
        """登録された集約からイベントを収集し、クリアする"""
        # セットをコピーしてループ（収集中にさらに追加される可能性に備える）
        aggregates = list(self._registered_aggregates)
        # 収集済みとして一旦クリア
        self._registered_aggregates.clear()
        
        for aggregate in aggregates:
            if hasattr(aggregate, 'get_events') and hasattr(aggregate, 'clear_events'):
                events = aggregate.get_events()
                if events:
                    self._pending_events.extend(events)
                    aggregate.clear_events()

    def get_pending_events(self) -> List[DomainEvent]:
        """保留中のイベントを取得（テスト用）"""
        return self._pending_events.copy()

    def clear_pending_events(self) -> None:
        """保留中のイベントをクリア"""
        self._pending_events.clear()

    def is_in_transaction(self) -> bool:
        """トランザクション中かどうかを返す（テスト用）"""
        return self._in_transaction

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

        unit_of_work = cls(unit_of_work_factory=unit_of_work_factory, data_store=data_store)
        event_publisher = InMemoryEventPublisherWithUow(unit_of_work)
        unit_of_work._event_publisher = event_publisher
        return unit_of_work, event_publisher
