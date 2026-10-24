"""共通の配送器が、ゲームに依存せず確定前後の受け手を呼べることを保証する。"""

from datetime import datetime, timezone

import pytest

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.eventing.delivery import DeliveryChannel, DeliveryGuarantee
from ai_rpg_world.eventing.dispatcher import EventDispatcher


def test_common_event_is_dispatched_with_callers_context() -> None:
    """共通のイベントを配送すると、呼び出す側が渡した文脈を確定前の受け手へ渡す。"""
    context = object()
    event = DomainEvent(1, datetime.now(timezone.utc))
    calls: list[tuple[DomainEvent, object]] = []
    dispatcher = EventDispatcher[object](failure_observer=lambda *args: None)
    dispatcher.register_required_before_commit(DomainEvent, lambda e, c: calls.append((e, c)))
    dispatcher.dispatch(event, context)
    assert calls == [(event, context)]


def test_failure_observer_is_required() -> None:
    """知らせ先を省略して配送器を組み立てると、その場で拒否する。"""
    with pytest.raises(TypeError, match="failure_observer"):
        EventDispatcher[object]()


def test_failure_observer_cannot_be_none() -> None:
    """知らせ先に None を渡すと、受け手の失敗を見逃す構成として拒否する。"""
    with pytest.raises(TypeError, match="failure_observer"):
        EventDispatcher[object](failure_observer=None)


@pytest.mark.parametrize("durable_only", [False, True])
def test_later_event_runs_after_durable_failure(durable_only: bool) -> None:
    """初回配送と再送のどちらも、一つのイベントで失敗しても後続のイベントを試す。"""
    attempted: list[int] = []
    dispatcher = EventDispatcher[object](failure_observer=lambda *args: None)

    def handle(event: DomainEvent) -> None:
        attempted.append(event.event_id)
        if event.event_id == 1:
            raise RuntimeError("first failed")

    dispatcher.register_after_commit(
        DomainEvent, handle, channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY
    )
    deliver = dispatcher.handoff_durable if durable_only else dispatcher.handoff
    with pytest.raises(RuntimeError, match="first failed"):
        deliver([DomainEvent(i, datetime.now(timezone.utc)) for i in (1, 2)])
    assert attempted == [1, 2]


@pytest.mark.parametrize("durable_only", [False, True])
def test_first_durable_error_is_preserved(durable_only: bool) -> None:
    """再送必須の受け手が複数失敗すると、最後まで呼んだ後に最初の例外そのものを返す。"""
    dispatcher = EventDispatcher[object](failure_observer=lambda *args: None)
    errors = [RuntimeError("first"), ValueError("second")]
    attempted: list[Exception] = []

    def first(event: DomainEvent) -> None:
        attempted.append(errors[0])
        raise errors[0]

    def second(event: DomainEvent) -> None:
        attempted.append(errors[1])
        raise errors[1]

    for handler in (first, second):
        dispatcher.register_after_commit(
            DomainEvent, handler, channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY
        )
    deliver = dispatcher.handoff_durable if durable_only else dispatcher.handoff
    with pytest.raises(RuntimeError) as caught:
        deliver([DomainEvent(1, datetime.now(timezone.utc))])
    assert attempted == errors
    assert caught.value is errors[0]


@pytest.mark.parametrize("durable_only", [False, True])
def test_every_durable_failure_is_observed(durable_only: bool) -> None:
    """再送必須の受け手が二件のイベントで失敗すると、初回配送・再送とも二件の失敗を知らせる。"""
    failures: list[tuple[int, Exception]] = []
    dispatcher = EventDispatcher[object](
        failure_observer=lambda channel, guarantee, event, handler, error: failures.append((event.event_id, error))
    )
    error = RuntimeError("delivery failed")

    def fail(event: DomainEvent) -> None:
        raise error

    dispatcher.register_after_commit(
        DomainEvent, fail, channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY
    )
    deliver = dispatcher.handoff_durable if durable_only else dispatcher.handoff
    with pytest.raises(RuntimeError):
        deliver([DomainEvent(i, datetime.now(timezone.utc)) for i in (1, 2)])
    assert failures == [(1, error), (2, error)]
