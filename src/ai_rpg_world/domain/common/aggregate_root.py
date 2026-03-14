from typing import Any, List

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


class AggregateRoot:
    """集約ルートの基底クラス"""

    def __init__(self):
        self._events: List[BaseDomainEvent[Any, Any]] = []

    def add_event(self, event: BaseDomainEvent[Any, Any]) -> None:
        """ドメインイベントを追加"""
        self._events.append(event)

    def get_events(self) -> List[BaseDomainEvent[Any, Any]]:
        """未発行のイベントを取得"""
        return self._events.copy()
    
    def clear_events(self) -> None:
        """イベントをクリア"""
        self._events.clear()