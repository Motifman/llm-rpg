from abc import ABC, abstractmethod
from typing import List
from src.domain.common.domain_event import DomainEvent


class EventPublisher(ABC):
    """イベント発行者のインターフェース"""
    
    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """単一イベントを発行"""
        pass
    
    @abstractmethod
    def publish_all(self, events: List[DomainEvent]) -> None:
        """複数イベントを一括発行"""
        pass