"""Outbox-ready seam の契約検証テスト (Phase 6)

EventPayloadSerializer と AsyncEventTransport の port 契約が
将来の outbox 実装で差し替え可能であることを検証する。
実装はテスト内で定義し、production コードには追加しない。
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


# --- EventPayloadSerializer 契約検証用の最小実装 ---


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


# --- AsyncEventTransport 契約検証用の in-process 互換実装 ---


class InProcessAsyncEventTransport:
    """AsyncEventTransport 契約を満たす in-process 実装

    dispatch で即 Executor に委譲する。SEAM.md の「将来 Transport を挿入」時の
    in-process 実装の参照。
    """

    def __init__(self, executor: AsyncEventExecutor) -> None:
        self._executor = executor

    def dispatch(self, envelopes: Sequence[AsyncDispatchTask]) -> None:
        self._executor.execute(envelopes)


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
