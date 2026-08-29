"""CommandScopeが同期イベントとcommit後handoffの確定順序を守ることを保証する。"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import pytest

from ai_rpg_world.application.common.command_scope import (
    CommandCompletion,
    CommandContext,
    CommandScope,
)
from ai_rpg_world.application.common.transactional_outbox import StagedOutboxBatch
from ai_rpg_world.application.common.exceptions import (
    CommandPostCommitException,
    CommandEventDispatchLimitException,
    CommandScopeStateException,
    TransactionCommittedCleanupException,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent


class _RecordingTransaction:
    def __init__(self, timeline: Optional[list[str]] = None) -> None:
        self._active = False
        self.calls: list[str] = []
        self._timeline = timeline

    @property
    def is_active(self) -> bool:
        return self._active

    def begin(self) -> None:
        self.calls.append("begin")
        if self._timeline is not None:
            self._timeline.append("begin")
        self._active = True

    def commit(self) -> None:
        self.calls.append("commit")
        if self._timeline is not None:
            self._timeline.append("commit")
        self._active = False

    def rollback(self) -> None:
        self.calls.append("rollback")
        if self._timeline is not None:
            self._timeline.append("rollback")
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
    def __init__(
        self,
        error: Optional[Exception] = None,
        timeline: Optional[list[str]] = None,
    ) -> None:
        self.batches: list[tuple[DomainEvent, ...]] = []
        self._error = error
        self._timeline = timeline

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        self.batches.append(tuple(events))
        if self._timeline is not None:
            self._timeline.append("handoff")
        if self._error is not None:
            raise self._error


class _NoOpDispatcher:
    def dispatch(self, event: DomainEvent, context: CommandContext) -> None:
        pass


class _NoOpHandoff:
    def handoff(self, events: Sequence[DomainEvent]) -> None:
        pass


class _RecordingOutbox:
    """commit前登録とcommit後完了記録の順序を記録するoutbox fake。"""

    def __init__(
        self,
        *,
        timeline: Optional[list[str]] = None,
        stage_error: Optional[Exception] = None,
        mark_error: Optional[Exception] = None,
    ) -> None:
        self.calls: list[tuple[str, object]] = []
        self.batch = StagedOutboxBatch(event_ids=("1",))
        self._timeline = timeline
        self._stage_error = stage_error
        self._mark_error = mark_error

    def stage(self, events: Sequence[DomainEvent], transaction: object) -> StagedOutboxBatch:
        self.calls.append(("stage", tuple(events)))
        if self._timeline is not None:
            self._timeline.append("stage")
        if self._stage_error is not None:
            raise self._stage_error
        return self.batch

    def mark_delivered(self, batch: StagedOutboxBatch) -> None:
        self.calls.append(("mark_delivered", batch))
        if self._timeline is not None:
            self._timeline.append("mark_delivered")
        if self._mark_error is not None:
            raise self._mark_error


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

    def test_outbox_is_staged_before_commit_and_marked_after_handoff(self) -> None:
        """再送対象はcommit前に登録し、handoff成功後だけ配達済みにする。"""
        timeline: list[str] = []
        transaction = _RecordingTransaction(timeline)
        event = _event(1)
        outbox = _RecordingOutbox(timeline=timeline)
        handoff = _RecordingHandoff(timeline=timeline)

        with CommandScope(
            transaction,
            sync_dispatcher=_RecordingDispatcher(),
            after_commit_handoff=handoff,
            transactional_outbox=outbox,
        ) as context:
            context.collect(event)

        assert transaction.calls == ["begin", "commit"]
        assert outbox.calls == [
            ("stage", (event,)),
            ("mark_delivered", outbox.batch),
        ]
        assert handoff.batches == [(event,)]
        assert timeline == [
            "begin",
            "stage",
            "commit",
            "handoff",
            "mark_delivered",
        ]

    def test_handoff_failure_leaves_staged_outbox_pending(self) -> None:
        """commit後handoffが失敗するとoutboxを配達済みにせず再試行元を残す。"""
        outbox = _RecordingOutbox()
        handoff_error = RuntimeError("handoff failed")

        with pytest.raises(CommandPostCommitException):
            with CommandScope(
                _RecordingTransaction(),
                sync_dispatcher=_RecordingDispatcher(),
                after_commit_handoff=_RecordingHandoff(handoff_error),
                transactional_outbox=outbox,
            ) as context:
                context.collect(_event(1))

        assert [name for name, _ in outbox.calls] == ["stage"]

    def test_outbox_stage_failure_rolls_back_before_commit(self) -> None:
        """outbox登録失敗は業務transactionをrollbackし、handoffを開始しない。"""
        stage_error = RuntimeError("stage failed")
        transaction = _RecordingTransaction()
        handoff = _RecordingHandoff()

        with pytest.raises(RuntimeError) as caught:
            with CommandScope(
                transaction,
                sync_dispatcher=_RecordingDispatcher(),
                after_commit_handoff=handoff,
                transactional_outbox=_RecordingOutbox(stage_error=stage_error),
            ) as context:
                context.collect(_event(1))

        assert caught.value is stage_error
        assert transaction.calls == ["begin", "rollback"]
        assert handoff.batches == []

    def test_commit_failure_rolls_back_staged_outbox_and_skips_handoff(self) -> None:
        """commit失敗時は登録済みoutboxをrollbackし、配送も完了記録も行わない。"""
        commit_error = RuntimeError("commit failed")

        class _FailingCommitTransaction(_RecordingTransaction):
            def commit(self) -> None:
                self.calls.append("commit")
                raise commit_error

        transaction = _FailingCommitTransaction()
        outbox = _RecordingOutbox()
        handoff = _RecordingHandoff()

        with pytest.raises(RuntimeError) as caught:
            with CommandScope(
                transaction,
                sync_dispatcher=_RecordingDispatcher(),
                after_commit_handoff=handoff,
                transactional_outbox=outbox,
            ) as context:
                context.collect(_event(1))

        assert caught.value is commit_error
        assert transaction.calls == ["begin", "commit", "rollback"]
        assert [name for name, _ in outbox.calls] == ["stage"]
        assert handoff.batches == []

    def test_outbox_ack_failure_is_reported_after_commit(self) -> None:
        """配達済み記録の失敗はcommit済み状態を戻さず確定後例外として通知する。"""
        mark_error = RuntimeError("mark failed")
        transaction = _RecordingTransaction()

        with pytest.raises(CommandPostCommitException) as caught:
            with CommandScope(
                transaction,
                sync_dispatcher=_RecordingDispatcher(),
                after_commit_handoff=_RecordingHandoff(),
                transactional_outbox=_RecordingOutbox(mark_error=mark_error),
            ) as context:
                context.collect(_event(1))

        assert caught.value.handoff_error is None
        assert caught.value.outbox_error is mark_error
        assert transaction.calls == ["begin", "commit"]

    def test_sync_failure_does_not_stage_outbox(self) -> None:
        """同期処理失敗時はoutboxへ未確定配送を登録しない。"""
        outbox = _RecordingOutbox()

        with pytest.raises(RuntimeError, match="sync failed"):
            with CommandScope(
                _RecordingTransaction(),
                sync_dispatcher=_RecordingDispatcher(
                    lambda _event, _context: (_ for _ in ()).throw(
                        RuntimeError("sync failed")
                    )
                ),
                after_commit_handoff=_RecordingHandoff(),
                transactional_outbox=outbox,
            ) as context:
                context.collect(_event(1))

        assert outbox.calls == []

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
