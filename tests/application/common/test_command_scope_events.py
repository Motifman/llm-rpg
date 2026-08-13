"""CommandScopeが同期イベントとcommit後handoffの確定順序を守ることを保証する。"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import pytest

from ai_rpg_world.application.common.command_scope import (
    CommandCompletion,
    CommandContext,
    CommandScope,
)
from ai_rpg_world.application.common.exceptions import (
    CommandPostCommitException,
    CommandEventDispatchLimitException,
    CommandScopeStateException,
    TransactionCommittedCleanupException,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent


class _RecordingTransaction:
    def __init__(self) -> None:
        self._active = False
        self.calls: list[str] = []

    @property
    def is_active(self) -> bool:
        return self._active

    def begin(self) -> None:
        self.calls.append("begin")
        self._active = True

    def commit(self) -> None:
        self.calls.append("commit")
        self._active = False

    def rollback(self) -> None:
        self.calls.append("rollback")
        self._active = False


class _RecordingDispatcher:
    def __init__(
        self,
        callback: Optional[Callable[[DomainEvent, CommandContext], None]] = None,
    ) -> None:
        self.events: list[DomainEvent] = []
        self._callback = callback

    def dispatch(self, event: DomainEvent, context: CommandContext) -> None:
        self.events.append(event)
        if self._callback is not None:
            self._callback(event, context)


class _RecordingHandoff:
    def __init__(self, error: Optional[Exception] = None) -> None:
        self.batches: list[tuple[DomainEvent, ...]] = []
        self._error = error

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        self.batches.append(tuple(events))
        if self._error is not None:
            raise self._error


class _NoOpDispatcher:
    def dispatch(self, event: DomainEvent, context: CommandContext) -> None:
        pass


class _NoOpHandoff:
    def handoff(self, events: Sequence[DomainEvent]) -> None:
        pass


def _event(aggregate_id: int) -> DomainEvent:
    return BaseDomainEvent.create(aggregate_id, "test")


class TestCommandScopeSyncEvents:
    """同期イベントをqueueが空になるまで同じtransaction内で一度ずつ処理する。"""

    def test_handler_generated_event_is_dispatched_before_commit(self) -> None:
        """同期ハンドラが追加したイベントもcommit前に宣言順で処理する。"""
        transaction = _RecordingTransaction()
        first = _event(1)
        second = _event(2)

        def collect_second(event: DomainEvent, context: CommandContext) -> None:
            if event is first:
                context.collect(second)

        dispatcher = _RecordingDispatcher(collect_second)
        handoff = _RecordingHandoff()
        with CommandScope(
            transaction,
            sync_dispatcher=dispatcher,
            after_commit_handoff=handoff,
        ) as context:
            context.collect(first)

        assert dispatcher.events == [first, second]
        assert transaction.calls == ["begin", "commit"]
        assert handoff.batches == [(first, second)]

    def test_same_event_id_is_dispatched_once_across_multiple_drains(self) -> None:
        """処理済みイベントをハンドラが再収集しても操作全体では再処理しない。"""
        transaction = _RecordingTransaction()
        event = _event(1)
        dispatcher = _RecordingDispatcher(
            lambda handled, context: context.collect(handled)
        )

        with CommandScope(
            transaction,
            sync_dispatcher=dispatcher,
            after_commit_handoff=_RecordingHandoff(),
        ) as context:
            context.collect(event)

        assert dispatcher.events == [event]

    def test_dispatch_error_rolls_back_and_does_not_handoff(self) -> None:
        """同期ハンドラの例外ではcommitせずrollbackし、handoffを開始しない。"""
        transaction = _RecordingTransaction()
        dispatch_error = RuntimeError("dispatch failed")
        dispatcher = _RecordingDispatcher(
            lambda _event, _context: (_ for _ in ()).throw(dispatch_error)
        )
        handoff = _RecordingHandoff()

        with pytest.raises(RuntimeError) as caught:
            with CommandScope(
                transaction,
                sync_dispatcher=dispatcher,
                after_commit_handoff=handoff,
            ) as context:
                context.collect(_event(1))

        assert caught.value is dispatch_error
        assert transaction.calls == ["begin", "rollback"]
        assert handoff.batches == []

    def test_event_limit_rolls_back_infinite_chain(self) -> None:
        """同期イベント連鎖が上限を超えると無限継続せずcommand全体をrollbackする。"""
        transaction = _RecordingTransaction()
        dispatcher = _RecordingDispatcher(
            lambda event, context: context.collect(_event(event.aggregate_id + 1))
        )

        with pytest.raises(CommandEventDispatchLimitException):
            with CommandScope(
                transaction,
                sync_dispatcher=dispatcher,
                after_commit_handoff=_RecordingHandoff(),
                max_sync_events=2,
            ) as context:
                context.collect(_event(1))

        assert len(dispatcher.events) == 2
        assert transaction.calls == ["begin", "rollback"]


class TestCommandScopeAfterCommitHandoff:
    """commit後handoffの失敗を永続化失敗へ巻き戻さないことを保証する。"""

    def test_empty_command_handoffs_empty_batch_after_commit(self) -> None:
        """イベントがなくてもcommit成功後にhandoffを一度だけ呼ぶ。"""
        transaction = _RecordingTransaction()
        handoff = _RecordingHandoff()
        scope = CommandScope(
            transaction,
            sync_dispatcher=_RecordingDispatcher(),
            after_commit_handoff=handoff,
        )

        with scope:
            pass

        assert handoff.batches == [()]
        assert scope.completion is CommandCompletion.COMMITTED

    def test_handoff_error_does_not_rollback_committed_transaction(self) -> None:
        """handoff失敗を再送出してもcommit済みtransactionをrollbackしない。"""
        transaction = _RecordingTransaction()
        handoff_error = RuntimeError("handoff failed")
        scope = CommandScope(
            transaction,
            sync_dispatcher=_RecordingDispatcher(),
            after_commit_handoff=_RecordingHandoff(handoff_error),
        )

        with pytest.raises(CommandPostCommitException) as caught:
            with scope as context:
                context.collect(_event(1))

        assert caught.value.handoff_error is handoff_error
        assert caught.value.cleanup_error is None
        assert transaction.calls == ["begin", "commit"]
        assert scope.completion is CommandCompletion.COMMITTED

    def test_cleanup_and_handoff_errors_are_both_preserved_after_commit(self) -> None:
        """commit後の資源解放とhandoffが共に失敗しても両方を保持しrollbackしない。"""
        cleanup_error = RuntimeError("cleanup failed")
        handoff_error = RuntimeError("handoff failed")

        class _CommittedCleanupTransaction(_RecordingTransaction):
            def commit(self) -> None:
                super().commit()
                raise TransactionCommittedCleanupException(
                    cleanup_error=cleanup_error
                )

        transaction = _CommittedCleanupTransaction()
        scope = CommandScope(
            transaction,
            sync_dispatcher=_RecordingDispatcher(),
            after_commit_handoff=_RecordingHandoff(handoff_error),
        )

        with pytest.raises(CommandPostCommitException) as caught:
            with scope:
                pass

        assert caught.value.cleanup_error is cleanup_error
        assert caught.value.handoff_error is handoff_error
        assert transaction.calls == ["begin", "commit"]
        assert scope.completion is CommandCompletion.COMMITTED

    def test_handoff_keyboard_interrupt_is_not_downgraded_to_application_error(
        self,
    ) -> None:
        """commit後handoffのKeyboardInterruptはscopeを閉じた後も停止要求として伝播する。"""
        transaction = _RecordingTransaction()
        interrupt = KeyboardInterrupt()
        scope = CommandScope(
            transaction,
            sync_dispatcher=_RecordingDispatcher(),
            after_commit_handoff=_RecordingHandoff(interrupt),  # type: ignore[arg-type]
        )

        with pytest.raises(KeyboardInterrupt) as caught:
            with scope:
                pass

        assert caught.value is interrupt
        assert transaction.calls == ["begin", "commit"]
        assert scope.completion is CommandCompletion.COMMITTED

    def test_handoff_can_open_independent_command_scope(self) -> None:
        """commit後handoffは元scopeの外なので新しい独立commandを開始できる。"""
        outer_transaction = _RecordingTransaction()
        inner_transaction = _RecordingTransaction()

        class _OpeningHandoff:
            def handoff(self, events: Sequence[DomainEvent]) -> None:
                with CommandScope(
                    inner_transaction,
                    sync_dispatcher=_NoOpDispatcher(),
                    after_commit_handoff=_NoOpHandoff(),
                ):
                    pass

        with CommandScope(
            outer_transaction,
            sync_dispatcher=_NoOpDispatcher(),
            after_commit_handoff=_OpeningHandoff(),
        ):
            pass

        assert outer_transaction.calls == ["begin", "commit"]
        assert inner_transaction.calls == ["begin", "commit"]

    def test_context_rejects_collection_after_scope_closes(self) -> None:
        """終了したCommandContextへイベントを追加すると明示的な状態例外になる。"""
        with CommandScope(
            _RecordingTransaction(),
            sync_dispatcher=_RecordingDispatcher(),
            after_commit_handoff=_RecordingHandoff(),
        ) as context:
            pass

        with pytest.raises(CommandScopeStateException):
            context.collect(_event(1))
