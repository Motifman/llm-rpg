"""CommandScope用イベントdispatcherが相ごとの実行時期と失敗契約を守ることを保証する。"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from ai_rpg_world.application.common.command_scope import CommandContext, CommandScope
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent
from ai_rpg_world.infrastructure.events.phased_command_event_dispatcher import (
    PhasedCommandEventDispatcher,
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


def test_critical_sync_failure_rolls_back_and_skips_post_commit_handlers() -> None:
    """必須同期handlerが失敗するとtransactionを戻し、commit後handlerを呼ばない。"""
    transaction = _Transaction()
    calls: list[str] = []
    dispatcher = PhasedCommandEventDispatcher()
    dispatcher.register_critical_sync(
        BaseDomainEvent,
        lambda event, context: (_ for _ in ()).throw(RuntimeError("critical failed")),
    )
    dispatcher.register_async_post_commit(
        BaseDomainEvent,
        lambda event: calls.append("post_commit"),
    )

    with pytest.raises(RuntimeError, match="critical failed"):
        with CommandScope(
            transaction,
            sync_dispatcher=dispatcher,
            after_commit_handoff=dispatcher,
        ) as context:
            context.collect(_event())

    assert transaction.rolled_back is True
    assert transaction.committed is False
    assert calls == []


def test_best_effort_failure_is_observed_without_preventing_commit() -> None:
    """補助同期handlerの失敗は観測され、後続handlerとcommitを妨げない。"""
    transaction = _Transaction()
    calls: list[str] = []
    failures: list[tuple[str, BaseException]] = []
    dispatcher = PhasedCommandEventDispatcher(
        failure_observer=lambda phase, event, handler, error: failures.append(
            (phase.value, error)
        )
    )
    dispatcher.register_best_effort_sync(
        BaseDomainEvent,
        lambda event, context: (_ for _ in ()).throw(RuntimeError("aux failed")),
    )
    dispatcher.register_critical_sync(
        BaseDomainEvent,
        lambda event, context: calls.append("critical"),
    )

    with CommandScope(
        transaction,
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
    ) as context:
        context.collect(_event())

    assert transaction.committed is True
    assert calls == ["critical"]
    assert failures[0][0] == "best_effort_sync_side_effect"
    assert str(failures[0][1]) == "aux failed"


def test_sync_observation_failure_is_observed_without_preventing_commit() -> None:
    """同期観測の失敗は補助失敗として記録し、業務transactionを戻さない。"""
    transaction = _Transaction()
    failures: list[str] = []
    dispatcher = PhasedCommandEventDispatcher(
        failure_observer=lambda phase, event, handler, error: failures.append(
            phase.value
        )
    )
    dispatcher.register_sync_observation(
        BaseDomainEvent,
        lambda event, context: (_ for _ in ()).throw(
            RuntimeError("observation failed")
        ),
    )

    with CommandScope(
        transaction,
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
    ) as context:
        context.collect(_event())

    assert transaction.committed is True
    assert failures == ["sync_observation"]


def test_post_commit_failure_keeps_commit_and_uses_dedicated_exception() -> None:
    """commit後handlerの失敗は確定状態を戻さず専用例外として通知する。"""
    transaction = _Transaction()
    dispatcher = PhasedCommandEventDispatcher()
    dispatcher.register_async_post_commit(
        BaseDomainEvent,
        lambda event: (_ for _ in ()).throw(RuntimeError("delivery failed")),
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


def test_each_phase_runs_only_on_its_side_of_commit_in_registration_order() -> None:
    """同期3相はcommit前、通常観測と確定後配送はcommit後に登録順で実行する。"""
    transaction = _Transaction()
    calls: list[tuple[str, bool, bool]] = []
    dispatcher = PhasedCommandEventDispatcher()
    dispatcher.register_sync_observation(
        BaseDomainEvent,
        lambda event, context: calls.append(
            ("sync_observation", transaction.is_active, transaction.committed)
        ),
    )
    dispatcher.register_critical_sync(
        BaseDomainEvent,
        lambda event, context: calls.append(
            ("critical", transaction.is_active, transaction.committed)
        ),
    )
    dispatcher.register_observe_after_commit(
        BaseDomainEvent,
        lambda event: calls.append(
            ("observation", transaction.is_active, transaction.committed)
        ),
    )
    dispatcher.register_async_post_commit(
        BaseDomainEvent,
        lambda event: calls.append(
            ("delivery", transaction.is_active, transaction.committed)
        ),
    )

    with CommandScope(
        transaction,
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
    ) as context:
        context.collect(_event())

    assert calls == [
        ("sync_observation", True, False),
        ("critical", True, False),
        ("observation", False, True),
        ("delivery", False, True),
    ]


def test_unregistered_event_is_a_no_op() -> None:
    """handler未登録のイベントは同期・commit後のどちらでも何も実行しない。"""
    dispatcher = PhasedCommandEventDispatcher()
    context = CommandContext(DomainEventCollector())

    dispatcher.dispatch(_event(), context)
    dispatcher.handoff((_event(),))
