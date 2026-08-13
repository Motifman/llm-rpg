"""CommandScope用dispatcherが二相の実行時期と配送保証を守ることを保証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.common.command_scope import CommandContext, CommandScope
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)


class _Transaction:
    def __init__(self) -> None:
        self.is_active = False
        self.committed = False
        self.rolled_back = False

    def begin(self) -> None:
        self.is_active = True

    def commit(self) -> None:
        self.committed = True
        self.is_active = False

    def rollback(self) -> None:
        self.rolled_back = True
        self.is_active = False


def _event(event_id: int = 1) -> DomainEvent:
    return BaseDomainEvent(
        event_id=event_id,
        occurred_at=datetime.now(timezone.utc),
        aggregate_id="aggregate",
        aggregate_type="test",
    )


def test_required_failure_rolls_back_and_skips_after_commit_handlers() -> None:
    """commit前必須handlerが失敗するとtransactionを戻し、commit後処理を呼ばない。"""
    transaction = _Transaction()
    calls: list[str] = []
    dispatcher = CommandEventDispatcher()
    dispatcher.register_required_before_commit(
        BaseDomainEvent,
        lambda event, context: (_ for _ in ()).throw(RuntimeError("required failed")),
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: calls.append("after_commit"),
        channel=DeliveryChannel.READ_MODEL,
        guarantee=DeliveryGuarantee.DURABLE_RETRY,
    )

    with pytest.raises(RuntimeError, match="required failed"):
        with CommandScope(
            transaction,
            sync_dispatcher=dispatcher,
            after_commit_handoff=dispatcher,
        ) as context:
            context.collect(_event())

    assert transaction.rolled_back is True
    assert transaction.committed is False
    assert calls == []


def test_required_and_after_commit_handlers_run_on_their_side_in_order() -> None:
    """必須処理はcommit前、配送処理はcommit後に、それぞれ登録順で実行する。"""
    transaction = _Transaction()
    calls: list[tuple[str, bool, bool]] = []
    dispatcher = CommandEventDispatcher()
    dispatcher.register_required_before_commit(
        BaseDomainEvent,
        lambda event, context: calls.append(
            ("required-1", transaction.is_active, transaction.committed)
        ),
    )
    dispatcher.register_required_before_commit(
        BaseDomainEvent,
        lambda event, context: calls.append(
            ("required-2", transaction.is_active, transaction.committed)
        ),
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: calls.append(
            ("observation", transaction.is_active, transaction.committed)
        ),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: calls.append(
            ("read-model", transaction.is_active, transaction.committed)
        ),
        channel=DeliveryChannel.READ_MODEL,
        guarantee=DeliveryGuarantee.DURABLE_RETRY,
    )

    with CommandScope(
        transaction,
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
    ) as context:
        context.collect(_event())

    assert calls == [
        ("required-1", True, False),
        ("required-2", True, False),
        ("observation", False, True),
        ("read-model", False, True),
    ]


def test_best_effort_failure_is_observed_and_later_delivery_continues() -> None:
    """最善努力配送の失敗は記録され、後続のcommit後handlerを妨げない。"""
    transaction = _Transaction()
    calls: list[str] = []
    failures: list[tuple[str, str, str]] = []
    dispatcher = CommandEventDispatcher(
        failure_observer=lambda channel, guarantee, event, handler, error: (
            failures.append((channel.value, guarantee.value, str(error)))
        )
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: (_ for _ in ()).throw(RuntimeError("observation failed")),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: calls.append("later"),
        channel=DeliveryChannel.AUXILIARY,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    with CommandScope(
        transaction,
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
    ) as context:
        context.collect(_event())

    assert transaction.committed is True
    assert calls == ["later"]
    assert failures == [
        ("observation", "best_effort", "observation failed"),
    ]


def test_durable_retry_failure_keeps_commit_and_uses_dedicated_exception() -> None:
    """再送対象の配送失敗は確定状態を戻さず、確定後専用例外として通知する。"""
    transaction = _Transaction()
    dispatcher = CommandEventDispatcher()
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: (_ for _ in ()).throw(RuntimeError("delivery failed")),
        channel=DeliveryChannel.INTEGRATION,
        guarantee=DeliveryGuarantee.DURABLE_RETRY,
    )

    with pytest.raises(CommandPostCommitException) as caught:
        with CommandScope(
            transaction,
            sync_dispatcher=dispatcher,
            after_commit_handoff=dispatcher,
        ) as context:
            context.collect(_event())

    assert transaction.committed is True
    assert transaction.rolled_back is False
    assert str(caught.value.handoff_error) == "delivery failed"


@pytest.mark.parametrize(
    ("channel", "guarantee", "message"),
    [
        ("observation", DeliveryGuarantee.BEST_EFFORT, "DeliveryChannel"),
        (DeliveryChannel.OBSERVATION, "best_effort", "DeliveryGuarantee"),
    ],
)
def test_after_commit_registration_rejects_untyped_policy(
    channel: object,
    guarantee: object,
    message: str,
) -> None:
    """配送先・保証へ生文字列を渡すと登録時に拒否する。"""
    dispatcher = CommandEventDispatcher()

    with pytest.raises(TypeError, match=message):
        dispatcher.register_after_commit(
            BaseDomainEvent,
            lambda event: None,
            channel=channel,  # type: ignore[arg-type]
            guarantee=guarantee,  # type: ignore[arg-type]
        )


def test_unregistered_event_is_a_no_op() -> None:
    """handler未登録のイベントはcommit前・commit後のどちらでも何も実行しない。"""
    dispatcher = CommandEventDispatcher()
    context = CommandContext(DomainEventCollector())

    dispatcher.dispatch(_event(), context)
    dispatcher.handoff((_event(),))

    assert dispatcher.requires_durable_retry(_event()) is False


def test_durable_retry_selection_follows_registered_delivery_policy() -> None:
    """outbox対象判定はイベント型の固定表でなく登録済み配送保証から導出する。"""
    dispatcher = CommandEventDispatcher()
    event = _event()
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda handled: None,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    assert dispatcher.requires_durable_retry(event) is False

    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda handled: None,
        channel=DeliveryChannel.READ_MODEL,
        guarantee=DeliveryGuarantee.DURABLE_RETRY,
    )

    assert dispatcher.requires_durable_retry(event) is True


def test_outbox_handoff_invokes_only_durable_retry_handlers() -> None:
    """outbox再配送ではBEST_EFFORT handlerを重複実行せず、再送必須handlerだけ呼ぶ。"""
    dispatcher = CommandEventDispatcher()
    event = _event()
    calls: list[str] = []
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda _: calls.append("durable"),
        channel=DeliveryChannel.READ_MODEL,
        guarantee=DeliveryGuarantee.DURABLE_RETRY,
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda _: calls.append("best_effort"),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    dispatcher.handoff_durable((event,))

    assert calls == ["durable"]
