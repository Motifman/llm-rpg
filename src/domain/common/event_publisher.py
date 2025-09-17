from abc import ABC, abstractmethod
from typing import Generic, List, Type, TypeVar
from src.domain.common.domain_event import DomainEvent
from src.domain.common.event_handler import EventHandler


E = TypeVar('E', bound=DomainEvent)


class EventPublisher(ABC, Generic[E]):
    """イベント発行者のインターフェース"""
    
    @abstractmethod
    def register_handler(self, event_type: Type[E], handler: EventHandler[E]) -> None:
        """イベントハンドラーを登録"""
        pass
    
    @abstractmethod
    def publish(self, event: E) -> None:
        """単一イベントを発行"""
        pass
    
    @abstractmethod
    def publish_all(self, events: List[E]) -> None:
        """複数イベントを一括発行"""
        pass