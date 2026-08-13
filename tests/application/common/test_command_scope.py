"""CommandScopeがtransactionの一方向状態遷移と失敗契約を守ることを保証する。"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from ai_rpg_world.application.common.command_scope import (
    CommandCompletion,
    CommandScope,
    CommandScopeState,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.application.common.exceptions import (
    CommandRollbackException,
    CommandScopeStateException,
    NestedCommandScopeException,
)


class _RecordingTransaction:
    """begin・commit・rollbackの呼出しと失敗を記録するtransaction fake。"""

    def __init__(
        self,
        *,
        begin_error: Optional[Exception] = None,
        active_on_begin_error: bool = False,
        commit_error: Optional[Exception] = None,
        rollback_error: Optional[Exception] = None,
    ) -> None:
        self._active = False
        self.begin_error = begin_error
        self.active_on_begin_error = active_on_begin_error
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    @property
    def is_active(self) -> bool:
        return self._active

    def begin(self) -> None:
        if self._active:
            raise RuntimeError("transactionは開始済みです")
        self.begin_count += 1
        if self.begin_error is not None:
            self._active = self.active_on_begin_error
            raise self.begin_error
        self._active = True

    def commit(self) -> None:
        if not self._active:
            raise RuntimeError("transactionが開始されていません")
        self.commit_count += 1
        if self.commit_error is not None:
            raise self.commit_error
        self._active = False

    def rollback(self) -> None:
        if not self._active:
            raise RuntimeError("transactionが開始されていません")
        self.rollback_count += 1
        if self.rollback_error is not None:
            raise self.rollback_error
        self._active = False


class _NoOpSyncDispatcher:
    def dispatch(self, event: DomainEvent, context: object) -> None:
        pass


class _NoOpAfterCommitHandoff:
    def handoff(self, events: object) -> None:
        pass


class _RecordingRepositoryProviderFactory:
    """生成時のtransaction状態を記録し、指定したproviderを返すfake。"""

    def __init__(
        self,
        transaction: _RecordingTransaction,
        *,
        error: Optional[Exception] = None,
    ) -> None:
        self._transaction = transaction
        self._error = error
        self.provider = object()
        self.create_count = 0
        self.was_active_when_created = False

    def create(self, context: object) -> object:
        self.create_count += 1
        self.was_active_when_created = self._transaction.is_active
        if self._error is not None:
            raise self._error
        return self.provider


def _create_scope(transaction: _RecordingTransaction) -> CommandScope:
    return CommandScope(
        transaction,
        sync_dispatcher=_NoOpSyncDispatcher(),
        after_commit_handoff=_NoOpAfterCommitHandoff(),
    )


class TestCommandScopeSuccess:
    """正常なcommandが一度だけcommitされることを保証する。"""

    def test_empty_command_commits_once(self) -> None:
        """commandが正常終了するとbegin後に一度だけcommitする。"""
        transaction = _RecordingTransaction()
        scope = _create_scope(transaction)

        with scope:
            pass

        assert transaction.begin_count == 1
        assert transaction.commit_count == 1
        assert transaction.rollback_count == 0
        assert scope.state is CommandScopeState.CLOSED
        assert scope.completion is CommandCompletion.COMMITTED

    def test_repository_provider_is_created_after_transaction_begin(self) -> None:
        """providerはtransaction開始後に一度だけ生成され、contextから取得できる。"""
        transaction = _RecordingTransaction()
        factory = _RecordingRepositoryProviderFactory(transaction)
        scope = CommandScope(
            transaction,
            sync_dispatcher=_NoOpSyncDispatcher(),
            after_commit_handoff=_NoOpAfterCommitHandoff(),
            repository_provider_factory=factory,
        )

        with scope as context:
            assert context.repositories is factory.provider

        assert factory.create_count == 1
        assert factory.was_active_when_created is True

    def test_context_rejects_repository_access_after_scope_closes(self) -> None:
        """scope終了後のcontextはproviderを再取得できない。"""
        transaction = _RecordingTransaction()
        factory = _RecordingRepositoryProviderFactory(transaction)
        scope = CommandScope(
            transaction,
            sync_dispatcher=_NoOpSyncDispatcher(),
            after_commit_handoff=_NoOpAfterCommitHandoff(),
            repository_provider_factory=factory,
        )

        with scope as context:
            assert context.repositories is factory.provider

        with pytest.raises(CommandScopeStateException):
            _ = context.repositories


class TestCommandScopeRollback:
    """commandまたはcommit失敗がrollbackされ、例外情報を失わないことを保証する。"""

    def test_command_error_rolls_back_without_commit(self) -> None:
        """command本体の例外ではcommitせず一度だけrollbackして元例外を再送出する。"""
        transaction = _RecordingTransaction()
        scope = _create_scope(transaction)
        command_error = RuntimeError("command failed")

        with pytest.raises(RuntimeError) as caught:
            with scope:
                raise command_error

        assert caught.value is command_error
        assert transaction.commit_count == 0
        assert transaction.rollback_count == 1
        assert scope.completion is CommandCompletion.ROLLED_BACK

    def test_begin_error_rolls_back_partially_started_transaction(self) -> None:
        """begin途中でactiveになってから失敗したtransactionは終了前にrollbackする。"""
        begin_error = RuntimeError("begin failed")
        transaction = _RecordingTransaction(
            begin_error=begin_error,
            active_on_begin_error=True,
        )
        scope = _create_scope(transaction)

        with pytest.raises(RuntimeError) as caught:
            with scope:
                pass

        assert caught.value is begin_error
        assert transaction.rollback_count == 1
        assert transaction.is_active is False
        assert scope.completion is CommandCompletion.ROLLED_BACK
        assert scope.state is CommandScopeState.CLOSED

    def test_begin_and_rollback_errors_are_both_preserved(self) -> None:
        """begin途中失敗の後にrollbackも失敗すると両方の例外を保持する。"""
        begin_error = RuntimeError("begin failed")
        rollback_error = RuntimeError("rollback failed")
        transaction = _RecordingTransaction(
            begin_error=begin_error,
            active_on_begin_error=True,
            rollback_error=rollback_error,
        )
        scope = _create_scope(transaction)

        with pytest.raises(CommandRollbackException) as caught:
            with scope:
                pass

        assert caught.value.primary_error is begin_error
        assert caught.value.rollback_error is rollback_error
        assert scope.completion is CommandCompletion.ROLLBACK_FAILED
        assert scope.state is CommandScopeState.CLOSED

    def test_repository_provider_creation_error_rolls_back(self) -> None:
        """provider生成が失敗するとcommandを開始せずtransactionをrollbackする。"""
        transaction = _RecordingTransaction()
        provider_error = RuntimeError("provider failed")
        factory = _RecordingRepositoryProviderFactory(
            transaction,
            error=provider_error,
        )
        scope = CommandScope(
            transaction,
            sync_dispatcher=_NoOpSyncDispatcher(),
            after_commit_handoff=_NoOpAfterCommitHandoff(),
            repository_provider_factory=factory,
        )

        with pytest.raises(RuntimeError) as caught:
            with scope:
                pass

        assert caught.value is provider_error
        assert transaction.commit_count == 0
        assert transaction.rollback_count == 1
        assert scope.completion is CommandCompletion.ROLLED_BACK
        assert scope.state is CommandScopeState.CLOSED

    def test_commit_error_attempts_rollback(self) -> None:
        """commit失敗時は有効なtransactionを一度rollbackしてcommit例外を再送出する。"""
        commit_error = RuntimeError("commit failed")
        transaction = _RecordingTransaction(commit_error=commit_error)
        scope = _create_scope(transaction)

        with pytest.raises(RuntimeError) as caught:
            with scope:
                pass

        assert caught.value is commit_error
        assert transaction.commit_count == 1
        assert transaction.rollback_count == 1
        assert scope.completion is CommandCompletion.ROLLED_BACK

    @pytest.mark.parametrize("failure_site", ["command", "commit"])
    def test_rollback_error_preserves_primary_and_rollback_errors(
        self, failure_site: str
    ) -> None:
        """commandまたはcommit後のrollback失敗は最初とrollbackの例外を両方保持する。"""
        primary_error = RuntimeError(f"{failure_site} failed")
        rollback_error = RuntimeError("rollback failed")
        transaction = _RecordingTransaction(
            commit_error=primary_error if failure_site == "commit" else None,
            rollback_error=rollback_error,
        )
        scope = _create_scope(transaction)

        with pytest.raises(CommandRollbackException) as caught:
            with scope:
                if failure_site == "command":
                    raise primary_error

        assert caught.value.primary_error is primary_error
        assert caught.value.rollback_error is rollback_error
        assert transaction.rollback_count == 1
        assert scope.completion is CommandCompletion.ROLLBACK_FAILED
        assert scope.state is CommandScopeState.CLOSED


class TestCommandScopeGuards:
    """CommandScopeの再利用と暗黙の入れ子をtransaction開始前に拒否する。"""

    def test_nested_scope_is_rejected_before_inner_transaction_begins(self) -> None:
        """有効なscope内で別scopeを開くと内側transactionを開始せず拒否する。"""
        outer_transaction = _RecordingTransaction()
        inner_transaction = _RecordingTransaction()

        with _create_scope(outer_transaction):
            with pytest.raises(NestedCommandScopeException):
                with _create_scope(inner_transaction):
                    pass

        assert outer_transaction.commit_count == 1
        assert inner_transaction.begin_count == 0

    def test_closed_scope_cannot_be_reused(self) -> None:
        """一度終了したscopeを再度開始すると状態例外を送出する。"""
        scope = _create_scope(_RecordingTransaction())
        with scope:
            pass

        with pytest.raises(CommandScopeStateException):
            with scope:
                pass

    def test_child_task_may_open_scope_after_inherited_parent_is_closed(self) -> None:
        """生成時のContextVarに閉じた親scopeが残る子taskでも新scopeを開始できる。"""

        async def exercise() -> _RecordingTransaction:
            ready = asyncio.Event()
            release = asyncio.Event()
            child_transaction = _RecordingTransaction()

            async def child() -> None:
                ready.set()
                await release.wait()
                with _create_scope(child_transaction):
                    pass

            with _create_scope(_RecordingTransaction()):
                task = asyncio.create_task(child())
                await ready.wait()
            release.set()
            await task
            return child_transaction

        transaction = asyncio.run(exercise())
        assert transaction.begin_count == 1
        assert transaction.commit_count == 1
