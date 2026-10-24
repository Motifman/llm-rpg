"""application commandのcommit前処理とcommit後配送を表す契約。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.eventing.delivery import AfterCommitFailureObserver as AfterCommitFailureObserver
from ai_rpg_world.eventing.delivery import AfterCommitHandler as AfterCommitHandler
from ai_rpg_world.eventing.delivery import DeliveryChannel as DeliveryChannel
from ai_rpg_world.eventing.delivery import DeliveryGuarantee as DeliveryGuarantee

RequiredBeforeCommitHandler = Callable[[DomainEvent, CommandContext[Any]], None]
# 登録時に event_type と handler の型を結ぶ。結ばないと、handler の中で
# そのイベント固有の属性を読めない (基底型として渡ってくる)。
_Event = TypeVar("_Event", bound=DomainEvent)


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
