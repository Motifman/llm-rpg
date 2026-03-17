"""InMemoryEventPublisherWithUow のテスト"""

import pytest

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
    InMemoryEventPublisherWithUow,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class FailingAsyncHandler(EventHandler[BaseDomainEvent]):
    """テスト用: handle で例外を投げる非同期ハンドラ"""

    def handle(self, event: BaseDomainEvent) -> None:
        raise RuntimeError("Async handler failed intentionally")


class TestInMemoryEventPublisherWithUow:
    """InMemoryEventPublisherWithUow のテスト"""

    def test_publish_pending_events_propagates_async_handler_exception(self):
        """非同期ハンドラが例外を投げた場合、握りつぶさず呼び出し元に伝播する"""
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        unit_of_work._event_publisher = event_publisher

        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        event_publisher.register_handler(
            type(event), FailingAsyncHandler(), is_synchronous=False
        )

        with pytest.raises(RuntimeError, match="Async handler failed intentionally"):
            with unit_of_work:
                unit_of_work.add_events([event])
