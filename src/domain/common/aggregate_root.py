from typing import List
from src.domain.common.domain_event import DomainEvent


class AggregateRoot:
    """集約ルートの基底クラス"""
    
    def __init__(self):
        self._events: List[DomainEvent] = []
    
    def add_event(self, event: DomainEvent) -> None:
        """ドメインイベントを追加"""
        self._events.append(event)
    
    def get_events(self) -> List[DomainEvent]:
        """未発行のイベントを取得"""
        return self._events.copy()
    
    def clear_events(self) -> None:
        """イベントをクリア"""
        self._events.clear()