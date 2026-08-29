"""集約イベントの収集入口がCommandContextだけになることを保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.common.aggregate_event_sink import (
    CommandContextAggregateEventSink,
)
from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


class _Aggregate:
    def __init__(self, events: list[BaseDomainEvent]) -> None:
        self.events = events
        self.clear_count = 0

    def get_events(self) -> list[BaseDomainEvent]:
        return list(self.events)

    def clear_events(self) -> None:
        self.events.clear()
        self.clear_count += 1


def _event(event_id: int) -> BaseDomainEvent:
    return BaseDomainEvent(
        event_id=event_id,
        occurred_at=datetime.now(timezone.utc),
        aggregate_id="aggregate",
        aggregate_type="test",
    )


def test_sink_moves_events_in_order_and_clears_aggregate_after_collection() -> None:
    """有効なscopeでは宣言順に収集し、全件成功後だけaggregateのqueueを空にする。"""
    collector = DomainEventCollector()
    context = CommandContext(collector)
    first = _event(1)
    second = _event(2)
    aggregate = _Aggregate([first, second])
    sink = CommandContextAggregateEventSink(context, is_active=lambda: True)

    sink.add_events_from_aggregate(aggregate)

    assert collector.drain() == [first, second]
    assert aggregate.events == []
    assert aggregate.clear_count == 1


def test_sink_deduplicates_same_event_id_through_command_context() -> None:
    """同じevent_idを持つイベントは一つのcommandで一度だけ収集する。"""
    collector = DomainEventCollector()
    context = CommandContext(collector)
    first = _event(1)
    duplicate = _event(1)
    aggregate = _Aggregate([first, duplicate])
    sink = CommandContextAggregateEventSink(context, is_active=lambda: True)

    sink.add_events_from_aggregate(aggregate)

    assert collector.drain() == [first]
    assert aggregate.events == []


def test_inactive_sink_rejects_collection_without_clearing_aggregate() -> None:
    """transaction終了後の収集は拒否し、未配送イベントをaggregateへ残す。"""
    context = CommandContext(DomainEventCollector())
    pending = _event(1)
    aggregate = _Aggregate([pending])
    sink = CommandContextAggregateEventSink(context, is_active=lambda: False)

    with pytest.raises(CommandScopeStateException):
        sink.add_events_from_aggregate(aggregate)

    assert aggregate.events == [pending]
    assert aggregate.clear_count == 0


def test_collection_failure_does_not_clear_aggregate() -> None:
    """不正イベントが混じる場合は一件も収集せず、aggregateのqueueを消さない。"""
    collector = DomainEventCollector()
    context = CommandContext(collector)
    valid = _event(1)
    invalid = object()
    aggregate = _Aggregate([valid, invalid])  # type: ignore[list-item]
    sink = CommandContextAggregateEventSink(context, is_active=lambda: True)

    with pytest.raises(ValueError, match="event_id"):
        sink.add_events_from_aggregate(aggregate)

    assert aggregate.events == [valid, invalid]
    assert aggregate.clear_count == 0
    assert collector.drain() == []
