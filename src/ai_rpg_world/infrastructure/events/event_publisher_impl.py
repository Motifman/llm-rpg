from typing import Dict, List, Type
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher


class InMemoryEventPublisher(EventPublisher[DomainEvent]):
    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}
        self._published_events: List[DomainEvent] = []

    def register_handler(
        self,
        event_type: Type[DomainEvent],
        handler: EventHandler[DomainEvent],
        is_synchronous: bool = False,
    ) -> None:
        """EventPublisher 契約に従い is_synchronous を受け取る（本実装は sync/async を区別せず全ハンドラを即時実行）"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent):
        # テスト用にイベントを記録
        self._published_events.append(event)

        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler.handle(event)
            except Exception as e:
                print(f"Error handling event {event_type}: {e}")

    def publish_all(self, events: List[DomainEvent]):
        for event in events:
            self.publish(event)

    def publish_async_events(self, events: List[DomainEvent]) -> None:
        """EventPublisher 契約: post-commit handoff。本実装は sync/async を区別せず全ハンドラを即時実行する"""
        for event in events:
            self._published_events.append(event)
            event_type = type(event)
            handlers = self._handlers.get(event_type, [])
            for handler in handlers:
                try:
                    handler.handle(event)
                except Exception as e:
                    print(f"Error handling event {event_type}: {e}")

    def get_published_events(self) -> List[DomainEvent]:
        """テスト用：発行されたイベントを取得"""
        return self._published_events.copy()

    def clear_events(self) -> None:
        """テスト用：発行されたイベントをクリア"""
        self._published_events.clear()