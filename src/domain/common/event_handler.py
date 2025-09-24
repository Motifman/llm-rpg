from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from src.domain.common.domain_event import DomainEvent

E = TypeVar('E', bound=DomainEvent)

class EventHandler(ABC, Generic[E]):
    @abstractmethod
    def handle(self, event: E):
        pass
