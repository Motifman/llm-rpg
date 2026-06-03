from collections import deque
from typing import Deque, Dict, List, Type
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher


# 長走 (140+ tick × 複数 agent) で _published_events が無限に肥える地雷を
# 防ぐための上限。test では fixture が publisher を毎回作り直すので、典型
# テストの 1 ケースで 10k events を超えることは無いと判断してこの値に。
# 超過したら deque が古い event を黙って捨てる。get_published_events() の
# 戻り値は「最新 N 件」になる。
_MAX_PUBLISHED_EVENTS = 10_000


class InMemoryEventPublisher(EventPublisher[DomainEvent]):
    def __init__(self):
        self._handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}
        self._published_events: Deque[DomainEvent] = deque(maxlen=_MAX_PUBLISHED_EVENTS)

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
            handler.handle(event)

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
                handler.handle(event)

    def get_published_events(self) -> List[DomainEvent]:
        """テスト用：発行されたイベントを取得 (deque を list 化したコピーを返す)。

        deque は上限 ``_MAX_PUBLISHED_EVENTS`` で循環する。超過した古い
        event は黙って捨てられる。長走のテストでこの上限を超える場合は
        deque の maxlen を引き上げるか、production 経路から本リスト依存
        を排除すること。
        """
        return list(self._published_events)

    def clear_events(self) -> None:
        """テスト用：発行されたイベントをクリア"""
        self._published_events.clear()