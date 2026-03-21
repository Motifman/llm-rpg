"""EventPublisher registration 契約のテスト

Phase 1 (uow-event-publisher-ddd-separation): 全 EventPublisher 実装が
register_handler(event_type, handler, is_synchronous=...) の同一契約を持つことを検証する。

Phase 7: post-commit handoff 契約 - 全実装が publish_async_events(events) を持ち、
TransactionalScope が抽象型経由で post-commit orchestration を行えることを検証する。
"""

import pytest

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.infrastructure.events.async_event_publisher import AsyncEventPublisher
from ai_rpg_world.infrastructure.events.event_publisher_impl import InMemoryEventPublisher
from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
    InMemoryEventPublisherWithUow,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class DummyHandler(EventHandler[BaseDomainEvent]):
    def handle(self, event: BaseDomainEvent) -> None:
        pass


class TestEventPublisherRegistrationContract:
    """全 EventPublisher 実装が is_synchronous 付き register_handler 契約を満たす"""

    def test_in_memory_event_publisher_accepts_is_synchronous(self):
        """InMemoryEventPublisher が is_synchronous 付きで登録できる"""
        publisher = InMemoryEventPublisher()
        event_type = BaseDomainEvent
        handler = DummyHandler()
        publisher.register_handler(event_type, handler, is_synchronous=True)
        publisher.register_handler(event_type, handler, is_synchronous=False)
        # 例外なく完了すればOK

    def test_async_event_publisher_accepts_is_synchronous(self):
        """AsyncEventPublisher が is_synchronous 付きで登録できる"""
        publisher = AsyncEventPublisher()
        event_type = BaseDomainEvent
        handler = DummyHandler()
        publisher.register_handler(event_type, handler, is_synchronous=True)
        publisher.register_handler(event_type, handler, is_synchronous=False)
        # 例外なく完了すればOK

    def test_in_memory_event_publisher_with_uow_accepts_is_synchronous(self):
        """InMemoryEventPublisherWithUow が is_synchronous 付きで登録できる"""
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)
        uow, publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        event_type = BaseDomainEvent
        handler = DummyHandler()
        publisher.register_handler(event_type, handler, is_synchronous=True)
        publisher.register_handler(event_type, handler, is_synchronous=False)
        # 例外なく完了すればOK


class TestEventPublisherPostCommitHandoffContract:
    """Phase 7: 全 EventPublisher 実装が publish_async_events(events) 契約を満たす

    TransactionalScope が EventPublisher 型としてのみ依存し、
    post-commit orchestration で publish_async_events を呼べることを検証する。
    """

    def test_in_memory_event_publisher_has_publish_async_events(self):
        """InMemoryEventPublisher が publish_async_events を提供する"""
        publisher: EventPublisher = InMemoryEventPublisher()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, DummyHandler(), is_synchronous=False)
        publisher.publish_async_events([event])  # 抽象経由で呼べる

    def test_async_event_publisher_has_publish_async_events(self):
        """AsyncEventPublisher が publish_async_events を提供する"""
        publisher: EventPublisher = AsyncEventPublisher()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, DummyHandler(), is_synchronous=False)
        publisher.publish_async_events([event])  # 抽象経由で呼べる

    def test_in_memory_event_publisher_with_uow_has_publish_async_events(self):
        """InMemoryEventPublisherWithUow が publish_async_events を提供する（抽象経由で呼び出し可能）"""
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)
        uow, publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, DummyHandler(), is_synchronous=False)
        ep: EventPublisher = publisher
        ep.publish_async_events([event])  # TransactionalScope と同様に抽象経由で呼び出し


class TestLegacyEventPublisherFailureSemantics:
    """Phase 10: 旧 InMemoryEventPublisher / AsyncEventPublisher はハンドラ例外を握りつぶさない"""

    class FailingHandler(EventHandler[BaseDomainEvent]):
        def handle(self, event: BaseDomainEvent) -> None:
            raise RuntimeError("handler failure")

    def test_in_memory_event_publisher_publish_propagates_handler_exception(self):
        publisher = InMemoryEventPublisher()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, self.FailingHandler(), is_synchronous=False)
        with pytest.raises(RuntimeError, match="handler failure"):
            publisher.publish(event)

    def test_in_memory_event_publisher_publish_async_events_propagates_handler_exception(self):
        publisher = InMemoryEventPublisher()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, self.FailingHandler(), is_synchronous=False)
        with pytest.raises(RuntimeError, match="handler failure"):
            publisher.publish_async_events([event])

    def test_async_event_publisher_publish_propagates_handler_exception(self):
        publisher = AsyncEventPublisher()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, self.FailingHandler(), is_synchronous=False)
        with pytest.raises(RuntimeError, match="handler failure"):
            publisher.publish(event)

    def test_async_event_publisher_publish_async_events_propagates_handler_exception(self):
        publisher = AsyncEventPublisher()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        publisher.register_handler(BaseDomainEvent, self.FailingHandler(), is_synchronous=False)
        with pytest.raises(RuntimeError, match="handler failure"):
            publisher.publish_async_events([event])
