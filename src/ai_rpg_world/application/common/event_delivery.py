"""application commandのcommit前処理とcommit後配送を表す契約。"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol, TypeVar

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


RequiredBeforeCommitHandler = Callable[[DomainEvent, CommandContext[Any]], None]
AfterCommitHandler = Callable[[DomainEvent], None]
# 登録時に event_type と handler の型を結ぶ。結ばないと、handler の中で
# そのイベント固有の属性を読めない (基底型として渡ってくる)。
_Event = TypeVar("_Event", bound=DomainEvent)
AfterCommitFailureObserver = Callable[
    [DeliveryChannel, DeliveryGuarantee, DomainEvent, object, Exception],
    None,
]


class CommandEventHandlerRegistrarPort(Protocol):
    """handlerをcommit前必須処理かcommit後配送へ登録するport。"""

    def register_required_before_commit(
        self,
        event_type: type[_Event],
        handler: Callable[[_Event, CommandContext[Any]], None],
    ) -> None: ...

    def register_after_commit(
        self,
        event_type: type[_Event],
        handler: Callable[[_Event], None],
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
