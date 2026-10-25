from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler

E = TypeVar("E", bound=DomainEvent)


class EventPublisher(ABC, Generic[E]):
    """イベント発行者のインターフェース"""

    @abstractmethod
    def register_handler(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """イベントハンドラーを登録"""
        pass

    @abstractmethod
    def publish(self, event: E) -> None:
        """単一イベントを発行"""
        pass

    @abstractmethod
    def publish_all(self, events: list[E]) -> None:
        """複数イベントを一括発行"""
        pass

    @abstractmethod
    def publish_async_events(self, events: list[E]) -> None:
        """指定イベントを非同期ハンドラで処理する（post-commit handoff API）

        UoW の pending に依存せず、明示的に渡されたイベントのみを処理する。
        post-commit orchestration から呼ばれることを想定。
        """
        pass
