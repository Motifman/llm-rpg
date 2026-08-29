"""1つのapplication commandのtransaction境界を統括するCommandScope。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from enum import Enum
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Iterable,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
)

from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import (
    CommandPostCommitException,
    CommandEventDispatchLimitException,
    CommandRollbackException,
    CommandScopeStateException,
    NestedCommandScopeException,
    TransactionCommittedCleanupException,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent

if TYPE_CHECKING:
    from ai_rpg_world.application.common.transactional_outbox import (
        StagedOutboxBatch,
        TransactionalOutboxPort,
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


class RollbackParticipantPort(Protocol):
    """repository外の可変状態を同じrollback境界へ参加させる最小契約。"""

    @property
    def rollback_resource(self) -> object:
        """二重参加を検出するため、実際に復元される資源の同一性を返す。"""
        ...

    def acquire_rollback_ownership(self) -> None:
        """snapshot取得前に資源を占有し、別commandの同時変更を防ぐ。"""
        ...

    def release_rollback_ownership(self) -> None:
        """commitまたはrollback完了後に資源の占有を解放する。"""
        ...

    def take_rollback_snapshot(self) -> Any:
        """command開始前の復元用snapshotを取得する。"""
        ...

    def restore_rollback_snapshot(self, snapshot: Any) -> None:
        """command失敗時に開始前snapshotへ戻す。"""
        ...

    def poison_after_rollback_failure(self, error: BaseException) -> None:
        """復元不能になった資源を後続commandから再利用不能にする。"""
        ...


class SyncDomainEventDispatcherPort(Protocol):
    """transaction内でドメインイベントを同期処理するport。"""

    def dispatch(self, event: DomainEvent, context: "CommandContext") -> None:
        """1件を処理し、追加イベントは同じcontextへ収集する。"""
        ...


class AfterCommitHandoffPort(Protocol):
    """commit済みイベントをtransaction外の配送開始点へ渡すport。"""

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        """確定済みイベントを配送側へ一度引き渡す。"""
        ...


RepositoryProviderT = TypeVar("RepositoryProviderT")


class RepositoryProviderFactoryPort(Protocol[RepositoryProviderT]):
    """開始済みcommand専用のrepository providerを生成するport。"""

    def create(
        self,
        context: "CommandContext[RepositoryProviderT]",
        transaction: TransactionPort,
    ) -> RepositoryProviderT:
        """現在のtransaction資源に参加するproviderを一度生成する。"""
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


class CommandContext(Generic[RepositoryProviderT]):
    """1 commandだけで有効なイベント収集・repository取得入口。"""

    def __init__(self, collector: DomainEventCollector) -> None:
        self._collector = collector
        self._seen_event_ids: set[int] = set()
        self._repository_provider: Optional[RepositoryProviderT] = None
        self._is_open = True

    @property
    def is_open(self) -> bool:
        """command内で利用可能な間だけTrueを返す。"""
        return self._is_open

    @property
    def repositories(self) -> RepositoryProviderT:
        """現在のtransactionへ参加した用途別repository providerを返す。"""
        self._require_open()
        if self._repository_provider is None:
            raise CommandScopeStateException(
                current_state=CommandScopeState.ACTIVE.value,
                attempted_operation="access_repositories_without_provider",
            )
        return self._repository_provider

    def collect(self, event: DomainEvent) -> None:
        """イベントを操作全体でevent_id重複なく収集する。"""
        self._require_open()
        event_id = getattr(event, "event_id", None)
        if event_id in self._seen_event_ids:
            return
        self._collector.add(event)
        self._seen_event_ids.add(event.event_id)

    def collect_all(self, events: Iterable[DomainEvent]) -> None:
        """複数イベントを宣言順に収集する。"""
        for event in events:
            self.collect(event)

    def _close(self) -> None:
        self._is_open = False

    def _bind_repository_provider(self, provider: RepositoryProviderT) -> None:
        self._require_open()
        if self._repository_provider is not None:
            raise CommandScopeStateException(
                current_state=CommandScopeState.ACTIVE.value,
                attempted_operation="bind_repository_provider_twice",
            )
        self._repository_provider = provider

    def _require_open(self) -> None:
        if self._is_open:
            return
        raise CommandScopeStateException(
            current_state=CommandScopeState.CLOSED.value,
            attempted_operation="collect_event",
        )


_ACTIVE_COMMAND_SCOPE: ContextVar[Optional["CommandScope"]] = ContextVar(
    "active_command_scope",
    default=None,
)


class CommandScope(Generic[RepositoryProviderT]):
    """同期イベントを収束後にcommitし、成功後だけhandoffする境界。"""

    def __init__(
        self,
        transaction: TransactionPort,
        *,
        sync_dispatcher: SyncDomainEventDispatcherPort,
        after_commit_handoff: AfterCommitHandoffPort,
        repository_provider_factory: Optional[
            RepositoryProviderFactoryPort[RepositoryProviderT]
        ] = None,
        transactional_outbox: Optional["TransactionalOutboxPort"] = None,
        max_sync_events: int = 1000,
    ) -> None:
        if (
            isinstance(max_sync_events, bool)
            or not isinstance(max_sync_events, int)
            or max_sync_events < 1
        ):
            raise ValueError("max_sync_eventsは1以上の整数である必要があります")
        self._transaction = transaction
        self._sync_dispatcher = sync_dispatcher
        self._after_commit_handoff = after_commit_handoff
        self._repository_provider_factory = repository_provider_factory
        self._transactional_outbox = transactional_outbox
        self._max_sync_events = max_sync_events
        self._collector = DomainEventCollector()
        self._context: CommandContext[RepositoryProviderT] = CommandContext(
            self._collector
        )
        self._dispatched_events: list[DomainEvent] = []
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

    def __enter__(self) -> CommandContext[RepositoryProviderT]:
        """新しいcommand境界を開始し、操作単位contextを返す。"""
        self._require_state(CommandScopeState.NEW, "begin")
        active_scope = _ACTIVE_COMMAND_SCOPE.get()
        if active_scope is not None and active_scope._is_transaction_active():
            raise NestedCommandScopeException()

        self._active_scope_token = _ACTIVE_COMMAND_SCOPE.set(self)
        try:
            self._transaction.begin()
        except BaseException as begin_error:
            if self._transaction.is_active:
                self._rollback_after(begin_error)
            self._close()
            raise
        self._state = CommandScopeState.ACTIVE
        if self._repository_provider_factory is not None:
            try:
                provider = self._repository_provider_factory.create(
                    self._context,
                    self._transaction,
                )
                self._context._bind_repository_provider(provider)
            except BaseException as provider_error:
                self._rollback_after(provider_error)
                raise
        return self._context

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        """同期処理とtransactionの成否に従って終了し、例外は握らない。"""
        self._require_state(CommandScopeState.ACTIVE, "finish")
        if exc_val is not None:
            self._rollback_after(exc_val)
            return False

        cleanup_error: Optional[BaseException] = None
        staged_outbox: Optional["StagedOutboxBatch"] = None
        try:
            self._dispatch_sync_events_until_empty()
            if self._transactional_outbox is not None:
                staged_outbox = self._transactional_outbox.stage(
                    tuple(self._dispatched_events),
                    self._transaction,
                )
            self._state = CommandScopeState.COMMITTING
            self._transaction.commit()
        except TransactionCommittedCleanupException as error:
            cleanup_error = error.cleanup_error
        except BaseException as primary_error:
            self._rollback_after(primary_error)
            raise

        self._state = CommandScopeState.COMMITTED
        self._completion = CommandCompletion.COMMITTED
        self._context._close()
        self._deactivate_active_scope()
        handoff_error: Optional[Exception] = None
        outbox_error: Optional[Exception] = None
        try:
            try:
                self._after_commit_handoff.handoff(tuple(self._dispatched_events))
            except Exception as error:
                handoff_error = error
            if (
                handoff_error is None
                and self._transactional_outbox is not None
                and staged_outbox is not None
            ):
                try:
                    self._transactional_outbox.mark_delivered(staged_outbox)
                except Exception as error:
                    outbox_error = error
        finally:
            self._close()
        if cleanup_error is not None and not isinstance(cleanup_error, Exception):
            post_commit_error = handoff_error or outbox_error
            if post_commit_error is not None:
                raise cleanup_error from post_commit_error
            raise cleanup_error
        if (
            cleanup_error is not None
            or handoff_error is not None
            or outbox_error is not None
        ):
            raise CommandPostCommitException(
                cleanup_error=cleanup_error,
                handoff_error=handoff_error,
                outbox_error=outbox_error,
            ) from (handoff_error or outbox_error or cleanup_error)
        return False

    def _dispatch_sync_events_until_empty(self) -> None:
        while True:
            events = self._collector.drain()
            if not events:
                return
            for event in events:
                if len(self._dispatched_events) >= self._max_sync_events:
                    raise CommandEventDispatchLimitException(
                        max_sync_events=self._max_sync_events,
                    )
                self._dispatched_events.append(event)
                self._sync_dispatcher.dispatch(event, self._context)

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
        self._collector.drain()
        self._context._close()
        self._deactivate_active_scope()
        self._state = CommandScopeState.CLOSED

    def _deactivate_active_scope(self) -> None:
        if self._active_scope_token is not None:
            _ACTIVE_COMMAND_SCOPE.reset(self._active_scope_token)
            self._active_scope_token = None

    def _is_transaction_active(self) -> bool:
        return self._state in {
            CommandScopeState.ACTIVE,
            CommandScopeState.COMMITTING,
            CommandScopeState.ROLLING_BACK,
        }


__all__ = [
    "AfterCommitHandoffPort",
    "CommandCompletion",
    "CommandContext",
    "CommandScope",
    "CommandScopeState",
    "RepositoryProviderFactoryPort",
    "RollbackParticipantPort",
    "SyncDomainEventDispatcherPort",
    "TransactionPort",
]
