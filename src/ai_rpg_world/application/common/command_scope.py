"""1つのapplication commandのtransaction境界を統括するCommandScope。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Optional, Protocol

from ai_rpg_world.application.common.exceptions import (
    CommandRollbackException,
    CommandScopeStateException,
    NestedCommandScopeException,
)


class TransactionPort(Protocol):
    """CommandScopeが必要とする永続化transactionの最小契約。"""

    @property
    def is_active(self) -> bool:
        """transactionが開始済みで未確定ならTrueを返す。"""
        ...

    def begin(self) -> None:
        """transactionを開始する。"""
        ...

    def commit(self) -> None:
        """transaction内の永続状態を確定する。"""
        ...

    def rollback(self) -> None:
        """transaction内の未確定変更を破棄する。"""
        ...


class CommandScopeState(str, Enum):
    """CommandScopeの一方向状態遷移。"""

    NEW = "new"
    ACTIVE = "active"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    CLOSED = "closed"


class CommandCompletion(str, Enum):
    """CommandScope終了後に残すtransactionの確定結果。"""

    NONE = "none"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    ROLLBACK_FAILED = "rollback_failed"


@dataclass(frozen=True)
class CommandContext:
    """後続PRでscope専用repositoryとイベントcollectorを載せる操作文脈。"""


_ACTIVE_COMMAND_SCOPE: ContextVar[Optional["CommandScope"]] = ContextVar(
    "active_command_scope",
    default=None,
)


class CommandScope:
    """command成功時だけcommitし、失敗時はrollbackする一度限りの境界。"""

    def __init__(self, transaction: TransactionPort) -> None:
        self._transaction = transaction
        self._context = CommandContext()
        self._state = CommandScopeState.NEW
        self._completion = CommandCompletion.NONE
        self._active_scope_token: Optional[Token[Optional["CommandScope"]]] = None

    @property
    def state(self) -> CommandScopeState:
        """現在の状態を返す。終了後はCLOSEDとなる。"""
        return self._state

    @property
    def completion(self) -> CommandCompletion:
        """transactionの確定結果を返す。"""
        return self._completion

    def __enter__(self) -> CommandContext:
        """新しいcommand境界を開始し、操作単位contextを返す。"""
        self._require_state(CommandScopeState.NEW, "begin")
        if _ACTIVE_COMMAND_SCOPE.get() is not None:
            raise NestedCommandScopeException()

        self._active_scope_token = _ACTIVE_COMMAND_SCOPE.set(self)
        try:
            self._transaction.begin()
        except BaseException:
            self._close()
            raise
        self._state = CommandScopeState.ACTIVE
        return self._context

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        """commandの成否に応じてcommitまたはrollbackし、例外は握らない。"""
        self._require_state(CommandScopeState.ACTIVE, "finish")
        if exc_val is not None:
            self._rollback_after(exc_val)
            return False

        try:
            self._state = CommandScopeState.COMMITTING
            self._transaction.commit()
        except BaseException as primary_error:
            self._rollback_after(primary_error)
            raise

        self._state = CommandScopeState.COMMITTED
        self._completion = CommandCompletion.COMMITTED
        self._close()
        return False

    def _rollback_after(self, primary_error: BaseException) -> None:
        self._state = CommandScopeState.ROLLING_BACK
        try:
            if self._transaction.is_active:
                self._transaction.rollback()
        except BaseException as rollback_error:
            self._completion = CommandCompletion.ROLLBACK_FAILED
            self._close()
            raise CommandRollbackException(
                primary_error=primary_error,
                rollback_error=rollback_error,
            ) from rollback_error

        self._state = CommandScopeState.ROLLED_BACK
        self._completion = CommandCompletion.ROLLED_BACK
        self._close()

    def _require_state(
        self,
        expected: CommandScopeState,
        operation: str,
    ) -> None:
        if self._state is expected:
            return
        raise CommandScopeStateException(
            current_state=self._state.value,
            attempted_operation=operation,
        )

    def _close(self) -> None:
        if self._active_scope_token is not None:
            _ACTIVE_COMMAND_SCOPE.reset(self._active_scope_token)
            self._active_scope_token = None
        self._state = CommandScopeState.CLOSED


__all__ = [
    "CommandCompletion",
    "CommandContext",
    "CommandScope",
    "CommandScopeState",
    "TransactionPort",
]
