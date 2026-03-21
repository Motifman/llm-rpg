from typing import Dict, List, Type
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher


class AsyncEventPublisher(EventPublisher[DomainEvent]):
    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}

    def register_handler(
        self,
        event_type: Type[DomainEvent],
        handler: EventHandler[DomainEvent],
        is_synchronous: bool = False,
    ) -> None:
        """EventPublisher 契約に従い is_synchronous を受け取る（本実装は非同期専用のため常に async として扱う）"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent):
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            handler.handle(event)

    def publish_all(self, events: List[DomainEvent]):
        for event in events:
            self.publish(event)

    def publish_async_events(self, events: List[DomainEvent]) -> None:
        """EventPublisher 契約: post-commit handoff。本実装は登録ハンドラを即時実行する"""
        for event in events:
            event_type = type(event)
            handlers = self._handlers.get(event_type, [])
            for handler in handlers:
                handler.handle(event)