"""未発行のイベントを集約自身にためる共通の基底。"""

from typing import Generic, TypeVar

from ai_rpg_world.eventing.domain_event import DomainEvent

_Event = TypeVar("_Event", bound=DomainEvent)


class AggregateRoot(Generic[_Event]):
    """集約ごとにイベントを保持し、配送する側へコピーを渡す。"""

    def __init__(self) -> None:
        self._events: list[_Event] = []

    def add_event(self, event: _Event) -> None:
        """起きたイベントを追加順にためる。"""
        self._events.append(event)

    def get_events(self) -> list[_Event]:
        """未発行のイベントの一覧をコピーして返す。"""
        return self._events.copy()

    def clear_events(self) -> None:
        """保持しているイベントをすべて取り除く。"""
        self._events.clear()
