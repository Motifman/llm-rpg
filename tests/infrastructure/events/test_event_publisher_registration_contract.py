"""EventPublisher registration 契約のテスト

Phase 1 (uow-event-publisher-ddd-separation): 全 EventPublisher 実装が
register_handler(event_type, handler, is_synchronous=...) の同一契約を持つことを検証する。
"""

import pytest

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
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
