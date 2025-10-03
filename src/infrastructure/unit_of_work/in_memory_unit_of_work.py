"""
InMemoryUnitOfWork - インメモリ実装のUnit of Work
実際のデータベーストランザクションは存在しないが、論理的なトランザクション境界を提供します。
"""
from typing import List, Callable, Any, Tuple, TYPE_CHECKING, Optional
from src.domain.common.unit_of_work import UnitOfWork
from src.domain.common.domain_event import DomainEvent

if TYPE_CHECKING:
    from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class InMemoryUnitOfWork(UnitOfWork):
    """インメモリ実装のUnit of Work

    実際のDBトランザクションはないが、論理的なトランザクション境界を提供し、
    複数の集約更新の一貫性を保証します。
    """

    def __init__(self, event_publisher=None, unit_of_work_factory=None):
        self._in_transaction = False
        self._pending_operations: List[Callable[[], None]] = []
        self._pending_events: List[DomainEvent] = []
        self._committed = False
        self._event_publisher = event_publisher

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
        self._committed = False

    def commit(self) -> None:
        """コミット - 保留中の操作を実行し、別トランザクションでイベント処理"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        try:
            # 保留中の操作を順次実行
            for operation in self._pending_operations:
                operation()

            self._committed = True

        except Exception as e:
            # コミット失敗時はロールバック
            self.rollback()
            raise e
        finally:
            # トランザクション完了後はクリア
            self._in_transaction = False
            self._pending_operations.clear()

            # コミット成功時のみ、別トランザクションでイベントを処理
            if self._committed and self._pending_events:
                self._process_events_in_separate_transaction()

            # イベントもクリア
            self._pending_events.clear()

    def _process_events_in_separate_transaction(self) -> None:
        """保留中のイベントを別トランザクションで処理"""
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
                        handlers = self._event_publisher._handlers.get(event_type, [])
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
        """ロールバック - 保留中の操作を破棄"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        # 保留中の操作をクリア
        self._pending_operations.clear()
        self._pending_events.clear()
        self._committed = False
        self._in_transaction = False

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
    def create_with_event_publisher(cls, unit_of_work_factory=None) -> Tuple["InMemoryUnitOfWork", "InMemoryEventPublisherWithUow"]:
        """Unit of Workとイベントパブリッシャーを作成し、適切に接続する

        双方向参照の設定をカプセル化し、テストでの使用を簡素化します。

        Args:
            unit_of_work_factory: 別トランザクション用のUnit of Workファクトリ（必須）

        Returns:
            (unit_of_work, event_publisher)のタプル
        """
        if unit_of_work_factory is None:
            raise ValueError("unit_of_work_factory is required for separate transaction event processing")

        # 実行時にインポートして循環インポートを回避
        from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow

        unit_of_work = cls(unit_of_work_factory=unit_of_work_factory)
        event_publisher = InMemoryEventPublisherWithUow(unit_of_work)
        unit_of_work._event_publisher = event_publisher
        return unit_of_work, event_publisher
