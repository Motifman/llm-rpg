"""InProcessAsyncEventExecutor のテスト (Phase 5)"""

import pytest

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.infrastructure.events.in_process_async_event_executor import (
    InProcessAsyncEventExecutor,
)


class RecordingHandler(EventHandler[BaseDomainEvent]):
    def __init__(self) -> None:
        self.handled: list[BaseDomainEvent] = []

    def handle(self, event: BaseDomainEvent) -> None:
        self.handled.append(event)


class TestInProcessAsyncEventExecutor:
    """InProcessAsyncEventExecutor のテスト"""

    def test_execute_runs_handlers_serially(self) -> None:
        """タスクを直列に実行し、全ハンドラが呼ばれる"""
        executor = InProcessAsyncEventExecutor()
        handler1 = RecordingHandler()
        handler2 = RecordingHandler()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")

        tasks = [(event, handler1), (event, handler2)]
        executor.execute(tasks)

        assert handler1.handled == [event]
        assert handler2.handled == [event]

    def test_execute_propagates_exception(self) -> None:
        """ハンドラが例外を投げた場合、握りつぶさず伝播する"""

        class FailingHandler(EventHandler[BaseDomainEvent]):
            def handle(self, event: BaseDomainEvent) -> None:
                raise ValueError("intentional failure")

        executor = InProcessAsyncEventExecutor()
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="Test")

        with pytest.raises(ValueError, match="intentional failure"):
            executor.execute([(event, FailingHandler())])
