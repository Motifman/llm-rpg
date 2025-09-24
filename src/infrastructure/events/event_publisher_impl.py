from typing import Dict, List, Type
from src.domain.common.domain_event import DomainEvent
from src.domain.common.event_handler import EventHandler
from src.domain.common.event_publisher import EventPublisher


class InMemoryEventPublisher(EventPublisher[DomainEvent]):
    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}

    def register_handler(self, event_type: Type[DomainEvent], handler: EventHandler[DomainEvent]):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent):
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