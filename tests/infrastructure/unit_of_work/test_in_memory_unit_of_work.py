"""
InMemoryUnitOfWorkのテスト
"""
import pytest
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.domain.common.domain_event import DomainEvent
from unittest.mock import Mock
from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class TestInMemoryUnitOfWork:
    """InMemoryUnitOfWorkのテスト"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        def create_unit_of_work():
            return InMemoryUnitOfWork(unit_of_work_factory=create_unit_of_work)
        self.unit_of_work = create_unit_of_work()

    def test_begin_starts_transaction(self):
        """トランザクション開始のテスト"""
        self.unit_of_work.begin()

        assert self.unit_of_work.is_in_transaction() is True
        assert self.unit_of_work.is_committed() is False

    def test_begin_twice_raises_error(self):
        """二重トランザクション開始のテスト"""
        self.unit_of_work.begin()

        with pytest.raises(RuntimeError, match="Transaction already in progress"):
            self.unit_of_work.begin()

    def test_commit_without_transaction_raises_error(self):
        """トランザクション外でのコミットテスト"""
        with pytest.raises(RuntimeError, match="No transaction in progress"):
            self.unit_of_work.commit()

    def test_rollback_without_transaction_raises_error(self):
        """トランザクション外でのロールバックテスト"""
        with pytest.raises(RuntimeError, match="No transaction in progress"):
            self.unit_of_work.rollback()

    def test_successful_transaction_with_context_manager(self):
        """コンテキストマネージャーを使った成功するトランザクションのテスト"""
        executed_operations = []

        with self.unit_of_work:
            # 保留中の操作を追加
            self.unit_of_work.add_operation(lambda: executed_operations.append("operation1"))
            self.unit_of_work.add_operation(lambda: executed_operations.append("operation2"))

        # トランザクションがコミットされ、操作が実行されたことを確認
        assert executed_operations == ["operation1", "operation2"]
        assert self.unit_of_work.is_committed() is True
        assert self.unit_of_work.is_in_transaction() is False

    def test_failed_transaction_with_context_manager(self):
        """コンテキストマネージャーを使った失敗するトランザクションのテスト"""
        executed_operations = []

        def failing_operation():
            executed_operations.append("failing")
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            with self.unit_of_work:
                # 保留中の操作を追加
                self.unit_of_work.add_operation(lambda: executed_operations.append("operation1"))
                self.unit_of_work.add_operation(lambda: executed_operations.append("operation2"))
                self.unit_of_work.add_operation(failing_operation)

        # InMemory実装では一度実行された操作を元に戻せないため、
        # 例外が発生する操作より前の操作は実行されてしまう
        # しかし、コミットは失敗し、トランザクションはロールバックされた状態になる
        assert executed_operations == ["operation1", "operation2", "failing"]
        assert self.unit_of_work.is_committed() is False
        assert self.unit_of_work.is_in_transaction() is False

    def test_add_operation_without_transaction_raises_error(self):
        """トランザクション外での操作追加テスト"""
        with pytest.raises(RuntimeError, match="No transaction in progress"):
            self.unit_of_work.add_operation(lambda: None)

    def test_add_events_without_transaction_raises_error(self):
        """トランザクション外でのイベント追加テスト"""
        event = Mock(spec=DomainEvent)

        with pytest.raises(RuntimeError, match="No transaction in progress"):
            self.unit_of_work.add_events([event])

    def test_event_publishing_with_event_publisher(self):
        """イベントパブリッシャーを使ったイベント発行テスト"""
        # モックイベントパブリッシャーを作成
        mock_event_publisher = Mock()
        mock_event_publisher.publish_pending_events = Mock()

        # Unit of Workにイベントパブリッシャーを設定
        self.unit_of_work._event_publisher = mock_event_publisher

        event1 = Mock(spec=DomainEvent)
        event2 = Mock(spec=DomainEvent)

        with self.unit_of_work:
            self.unit_of_work.add_events([event1, event2])

        # コミット時にイベントパブリッシャーのpublish_pending_eventsが呼ばれたことを確認
        mock_event_publisher.publish_pending_events.assert_called_once()

    def test_no_event_publishing_without_event_publisher(self):
        """イベントパブリッシャーが設定されていない場合のテスト"""
        event = Mock(spec=DomainEvent)

        with self.unit_of_work:
            self.unit_of_work.add_events([event])

        # イベントパブリッシャーが設定されていないので何も起こらない
        assert self.unit_of_work.is_committed() is True

    def test_pending_events_are_cleared_after_commit(self):
        """コミット後に保留中のイベントがクリアされるテスト"""
        event = Mock(spec=DomainEvent)
        self.unit_of_work._event_publisher = Mock()

        with self.unit_of_work:
            self.unit_of_work.add_events([event])

        # コミット後に保留中のイベントがクリアされていることを確認
        assert self.unit_of_work.get_pending_events() == []

    def test_pending_operations_are_cleared_after_commit(self):
        """コミット後に保留中の操作がクリアされるテスト"""
        with self.unit_of_work:
            self.unit_of_work.add_operation(lambda: None)

        # コミット後に保留中の操作がクリアされていることを確認
        # （内部的に_pending_operationsがクリアされる）
        assert len(self.unit_of_work._pending_operations) == 0

    def test_rollback_clears_pending_operations_and_events(self):
        """ロールバックで保留中の操作とイベントがクリアされるテスト"""
        event = Mock(spec=DomainEvent)

        self.unit_of_work.begin()
        self.unit_of_work.add_operation(lambda: None)
        self.unit_of_work.add_events([event])

        self.unit_of_work.rollback()

        # ロールバック後に保留中の操作とイベントがクリアされていることを確認
        assert len(self.unit_of_work._pending_operations) == 0
        assert self.unit_of_work.get_pending_events() == []

    def test_create_with_event_publisher_factory_method(self):
        """ファクトリーメソッドのテスト"""
        def create_unit_of_work():
            return InMemoryUnitOfWork(unit_of_work_factory=create_unit_of_work)
        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(unit_of_work_factory=create_unit_of_work)

        # Unit of Workが正しく作成されていることを確認
        assert isinstance(unit_of_work, InMemoryUnitOfWork)
        assert unit_of_work._event_publisher is event_publisher

        # イベントパブリッシャーが正しく作成されていることを確認
        assert event_publisher._unit_of_work is unit_of_work

        # 双方向参照が正しく設定されていることを確認
        assert unit_of_work._event_publisher is event_publisher
