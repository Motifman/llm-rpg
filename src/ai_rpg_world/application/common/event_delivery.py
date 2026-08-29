"""application commandのcommit前処理とcommit後配送を表す契約。"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Protocol, Type

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.domain.common.domain_event import DomainEvent


class DeliveryChannel(str, Enum):
    """commit後handlerの用途を表す。"""

    OBSERVATION = "observation"
    READ_MODEL = "read_model"
    INTEGRATION = "integration"
    AUXILIARY = "auxiliary"


class DeliveryGuarantee(str, Enum):
    """commit後handlerの失敗に必要な配送保証を表す。"""

    DURABLE_RETRY = "durable_retry"
    BEST_EFFORT = "best_effort"


RequiredBeforeCommitHandler = Callable[[DomainEvent, CommandContext], None]
AfterCommitHandler = Callable[[DomainEvent], None]
AfterCommitFailureObserver = Callable[
    [DeliveryChannel, DeliveryGuarantee, DomainEvent, object, Exception],
    None,
]


class CommandEventHandlerRegistrarPort(Protocol):
    """handlerをcommit前必須処理かcommit後配送へ登録するport。"""

    def register_required_before_commit(
        self,
        event_type: Type[DomainEvent],
        handler: RequiredBeforeCommitHandler,
    ) -> None: ...

    def register_after_commit(
        self,
        event_type: Type[DomainEvent],
        handler: AfterCommitHandler,
        *,
        channel: DeliveryChannel,
        guarantee: DeliveryGuarantee,
    ) -> None: ...


__all__ = [
    "AfterCommitFailureObserver",
    "AfterCommitHandler",
    "CommandEventHandlerRegistrarPort",
    "DeliveryChannel",
    "DeliveryGuarantee",
    "RequiredBeforeCommitHandler",
]
