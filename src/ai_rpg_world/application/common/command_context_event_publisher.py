"""CommandContextを既存EventPublisher形へ適合させる。"""

from collections.abc import Iterable
from typing import Any

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.domain.common.domain_event import DomainEvent


class CommandContextEventPublisher:
    """command中のeventを外へ配送せず、現在のcontextへ収集する。"""

    def __init__(self, context: CommandContext[Any]) -> None:
        self._context = context

    def publish(self, event: DomainEvent) -> None:
        self._context.collect(event)

    def publish_all(self, events: Iterable[DomainEvent]) -> None:
        self._context.collect_all(events)


__all__ = ["CommandContextEventPublisher"]
