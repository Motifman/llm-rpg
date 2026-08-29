"""集約イベントをcommand単位の収集入口へ移すadapter。"""

from __future__ import annotations

from typing import Any, Callable, Protocol, Sequence

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.domain.common.domain_event import DomainEvent


class EventProducingAggregatePort(Protocol):
    """未収集のドメインイベントを保持する集約の最小契約。"""

    def get_events(self) -> Sequence[DomainEvent]:
        """未収集イベントを宣言順に返す。"""
        ...

    def clear_events(self) -> None:
        """収集済みイベントを集約から取り除く。"""
        ...


class CommandContextAggregateEventSink:
    """集約イベントを旧Unit of Workへ渡さずCommandContextへ集約する。"""

    def __init__(
        self,
        context: CommandContext[Any],
        *,
        is_active: Callable[[], bool],
    ) -> None:
        self._context = context
        self._is_active = is_active

    def add_events_from_aggregate(
        self,
        aggregate: EventProducingAggregatePort,
    ) -> None:
        """全イベントの収集に成功した後だけaggregateのqueueを空にする。"""
        if not self._context.is_open or not self._is_active():
            raise CommandScopeStateException(
                current_state="closed",
                attempted_operation="collect_repository_events",
            )
        events = tuple(aggregate.get_events())
        self._validate_events(events)
        self._context.collect_all(events)
        aggregate.clear_events()

    @staticmethod
    def _validate_events(events: Sequence[DomainEvent]) -> None:
        """一部だけ収集してから失敗しないよう、全eventを先に検証する。"""
        for event in events:
            if not hasattr(event, "event_id"):
                raise ValueError(
                    "CommandContextAggregateEventSinkにはevent_idを持つ"
                    f"ドメインイベントだけを渡せます: {type(event).__name__}"
                )
            if event.event_id is None:
                raise ValueError(
                    "CommandContextAggregateEventSinkにはevent_id=Noneの"
                    f"イベントを渡せません: {type(event).__name__}"
                )


__all__ = [
    "CommandContextAggregateEventSink",
    "EventProducingAggregatePort",
]
