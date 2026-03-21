"""Outbox-ready seam の契約検証テスト (Phase 6 / Phase 8)

EventPayloadSerializer と AsyncEventTransport の port 契約が
将来の outbox 実装で差し替え可能であることを検証する。
Phase 8: InProcessAsyncEventTransport は production コードに存在。
EventPayloadSerializer は in-process では不使用のため、テスト内の Pickle 実装で契約検証。
"""
import pickle
from typing import Sequence

import pytest

from ai_rpg_world.domain.common.async_event_executor import (
    AsyncDispatchTask,
    AsyncEventExecutor,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.async_event_transport import AsyncEventTransport
from ai_rpg_world.domain.common.event_payload_serializer import EventPayloadSerializer
from ai_rpg_world.infrastructure.events.in_process_async_event_executor import (
    InProcessAsyncEventExecutor,
)
from ai_rpg_world.infrastructure.events.in_process_async_event_transport import (
    InProcessAsyncEventTransport,
)


# --- EventPayloadSerializer 契約検証用の最小実装（outbox 実装時の参照。in-process では不使用）---


class PickleEventPayloadSerializer:
    """EventPayloadSerializer 契約を満たすテスト用実装 (pickle ベース)

    outbox 実装時の参照。本番では JSON 等を検討する。
    """

    def serialize(self, event: BaseDomainEvent) -> bytes:
        return pickle.dumps(event)

    def deserialize(
        self, payload: bytes, event_type: type[BaseDomainEvent]
    ) -> BaseDomainEvent:
        return pickle.loads(payload)


# --- RecordingHandler (テスト用) ---


class RecordingHandler(EventHandler[BaseDomainEvent]):
    def __init__(self) -> None:
        self.handled: list[BaseDomainEvent] = []

    def handle(self, event: BaseDomainEvent) -> None:
        self.handled.append(event)


class TestEventPayloadSerializerSeam:
    """EventPayloadSerializer port の契約検証"""

    def test_pickle_serializer_roundtrip(self) -> None:
        """PickleEventPayloadSerializer が EventPayloadSerializer 契約を満たし、
        serialize → deserialize で roundtrip する"""
        serializer: EventPayloadSerializer = PickleEventPayloadSerializer()
        event = BaseDomainEvent.create(aggregate_id=42, aggregate_type="Test")

        payload = serializer.serialize(event)
        restored = serializer.deserialize(payload, type(event))

        assert restored.aggregate_id == event.aggregate_id
        assert restored.aggregate_type == event.aggregate_type
        assert restored.event_id == event.event_id


class TestAsyncEventTransportSeam:
    """AsyncEventTransport port の契約検証"""

    def test_in_process_transport_delegates_to_executor(self) -> None:
        """InProcessAsyncEventTransport が dispatch で Executor に委譲し、
        ハンドラが実行される"""
        executor = InProcessAsyncEventExecutor()
        transport: AsyncEventTransport = InProcessAsyncEventTransport(executor)
        handler = RecordingHandler()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")

        envelopes: Sequence[AsyncDispatchTask] = [(event, handler)]
        transport.dispatch(envelopes)

        assert handler.handled == [event]

    def test_transport_seam_swappable_with_executor(self) -> None:
        """Transport が Executor と組み合わせて動作し、
        既存の publish_async_events 相当のフローが Transport 経由でも成立する"""
        executor = InProcessAsyncEventExecutor()
        transport: AsyncEventTransport = InProcessAsyncEventTransport(executor)
        handler1 = RecordingHandler()
        handler2 = RecordingHandler()
        event = BaseDomainEvent.create(aggregate_id=99, aggregate_type="Multi")

        # EventPublisher._build_async_dispatch_tasks が生成する形と同じ
        tasks: list[AsyncDispatchTask] = [
            (event, handler1),
            (event, handler2),
        ]
        transport.dispatch(tasks)

        assert handler1.handled == [event]
        assert handler2.handled == [event]


class TestPhase8TransportProductionPath:
    """Phase 8: InMemoryEventPublisherWithUow が transport 経由で async publish する production path"""

    def test_publish_async_events_routes_through_transport(self) -> None:
        """InMemoryEventPublisherWithUow が async_transport 注入時に transport.dispatch 経由で配送する"""
        from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
            InMemoryEventPublisherWithUow,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        uow = InMemoryUnitOfWork(unit_of_work_factory=create_uow)
        executor = InProcessAsyncEventExecutor()
        dispatched: list[Sequence[AsyncDispatchTask]] = []

        class RecordingTransport:
            def __init__(self, delegate: AsyncEventExecutor):
                self._delegate = delegate
                self.dispatched: list[Sequence[AsyncDispatchTask]] = []

            def dispatch(self, envelopes: Sequence[AsyncDispatchTask]) -> None:
                self.dispatched.append(list(envelopes))
                self._delegate.execute(envelopes)

        transport = RecordingTransport(executor)
        handler = RecordingHandler()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")

        publisher = InMemoryEventPublisherWithUow(uow, async_transport=transport)
        publisher.register_handler(type(event), handler, is_synchronous=False)
        publisher.publish_async_events([event])

        assert len(transport.dispatched) == 1
        assert len(transport.dispatched[0]) == 1
        assert transport.dispatched[0][0][0] is event
        assert transport.dispatched[0][0][1] is handler
        assert handler.handled == [event]

    def test_create_with_event_publisher_uses_transport_path(self) -> None:
        """create_with_event_publisher が返す publisher が transport 経由で async ハンドラを実行する"""
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        scope, publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )

        handler = RecordingHandler()
        event = BaseDomainEvent.create(aggregate_id=99, aggregate_type="Test")
        publisher.register_handler(type(event), handler, is_synchronous=False)

        with scope:
            scope.add_events([event])

        assert handler.handled == [event]


class TestPublishAsyncEventsViaTransport:
    """Phase 8: InMemoryEventPublisherWithUow の publish_async_events が transport 経由で流れる検証"""

    def test_create_with_event_publisher_uses_transport_for_async_dispatch(self) -> None:
        """create_with_event_publisher で生成した publisher が transport 経由で async ハンドラを実行する"""
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        _, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        handler = RecordingHandler()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")
        event_publisher.register_handler(type(event), handler, is_synchronous=False)

        event_publisher.publish_async_events([event])

        # transport → executor 経由で handler が実行される
        assert handler.handled == [event]
