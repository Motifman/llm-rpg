"""application command内外で異なるイベント処理保証を表す契約。"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Protocol, Type

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.domain.common.domain_event import DomainEvent


class EventDeliveryPhase(str, Enum):
    """イベントhandlerを実行する時期と失敗方針を表す。"""

    CRITICAL_SYNC_SIDE_EFFECT = "critical_sync_side_effect"
    BEST_EFFORT_SYNC_SIDE_EFFECT = "best_effort_sync_side_effect"
    SYNC_OBSERVATION = "sync_observation"
    OBSERVE_AFTER_COMMIT = "observe_after_commit"
    ASYNC_POST_COMMIT = "async_post_commit"


InTransactionEventHandler = Callable[[DomainEvent, CommandContext], None]
AfterCommitEventHandler = Callable[[DomainEvent], None]
EventDeliveryFailureObserver = Callable[
    [EventDeliveryPhase, DomainEvent, object, BaseException],
    None,
]


class CommandEventHandlerRegistrarPort(Protocol):
    """各handlerを曖昧な真偽値なしで配送相へ登録するport。"""

    def register_critical_sync(
        self,
        event_type: Type[DomainEvent],
        handler: InTransactionEventHandler,
    ) -> None: ...

    def register_best_effort_sync(
        self,
        event_type: Type[DomainEvent],
        handler: InTransactionEventHandler,
    ) -> None: ...

    def register_sync_observation(
        self,
        event_type: Type[DomainEvent],
        handler: InTransactionEventHandler,
    ) -> None: ...

    def register_observe_after_commit(
        self,
        event_type: Type[DomainEvent],
        handler: AfterCommitEventHandler,
    ) -> None: ...

    def register_async_post_commit(
        self,
        event_type: Type[DomainEvent],
        handler: AfterCommitEventHandler,
    ) -> None: ...


__all__ = [
    "AfterCommitEventHandler",
    "CommandEventHandlerRegistrarPort",
    "EventDeliveryFailureObserver",
    "EventDeliveryPhase",
    "InTransactionEventHandler",
]
