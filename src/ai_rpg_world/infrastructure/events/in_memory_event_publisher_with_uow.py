"""
InMemoryEventPublisherWithUow - Unit of Workと統合されたインメモリイベントパブリッシャー
"""
from typing import Dict, List, Type
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class InMemoryEventPublisherWithUow(EventPublisher[DomainEvent]):
    """Unit of Workと統合されたインメモリイベントパブリッシャー

    イベントの発行をUnit of Workのトランザクション境界内で管理します。
    """

    def __init__(self, unit_of_work: InMemoryUnitOfWork):
        self._sync_handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}
        self._async_handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}
        self._published_events: List[DomainEvent] = []
        self._pending_events: List[DomainEvent] = []
        self._unit_of_work = unit_of_work

    def register_handler(self, event_type: Type[DomainEvent], handler: EventHandler[DomainEvent], is_synchronous: bool = False):
        """イベントハンドラーを登録"""
        target_dict = self._sync_handlers if is_synchronous else self._async_handlers
        if event_type not in target_dict:
            target_dict[event_type] = []
        target_dict[event_type].append(handler)

    def publish(self, event: DomainEvent):
        """単一のイベントを発行"""
        # Unit of Workのトランザクション内でのみ発行可能
        if not self._unit_of_work.is_in_transaction():
            raise RuntimeError("Event publishing must be within a transaction")

        # 保留中のイベントに追加
        self._unit_of_work.add_events([event])

    def publish_all(self, events: List[DomainEvent]):
        """複数のイベントを発行"""
        # Unit of Workのトランザクション内でのみ発行可能
        if not self._unit_of_work.is_in_transaction():
            raise RuntimeError("Event publishing must be within a transaction")

        # 保留中のイベントに追加
        self._unit_of_work.add_events(events)

    def publish_pending_events(self) -> None:
        """保留中のイベントを別トランザクションで処理（非同期ハンドラ用）"""
        # Unit of Workの保留イベントを取得、またはパブリッシャーの保留イベントを使用
        pending_events = self._pending_events if self._pending_events else self._unit_of_work.get_pending_events()

        for event in pending_events:
            # すでに記録済みの場合はスキップ（二重記録防止）
            if event not in self._published_events:
                self._published_events.append(event)

            # 登録された非同期ハンドラーで処理
            event_type = type(event)
            handlers = self._async_handlers.get(event_type, [])
            for handler in handlers:
                try:
                    handler.handle(event)
                except Exception as e:
                    print(f"Error handling async event {event_type}: {e}")

        # 発行済みのイベントをクリア
        if self._pending_events:
            self._pending_events.clear()
        else:
            self._unit_of_work.clear_pending_events()

    def publish_sync_events(self, events: List[DomainEvent]) -> None:
        """同期イベントを即時処理する（同一トランザクション内）"""
        for event in events:
            # すでに記録済みの場合はスキップ（二重記録防止）
            if event not in self._published_events:
                self._published_events.append(event)

            # 登録された同期ハンドラーで処理
            event_type = type(event)
            handlers = self._sync_handlers.get(event_type, [])
            for handler in handlers:
                # 同期ハンドラーは例外を上に投げる（トランザクション失敗のため）
                handler.handle(event)

    def get_published_events(self) -> List[DomainEvent]:
        """テスト用：発行されたイベントを取得"""
        return self._published_events.copy()

    def clear_events(self) -> None:
        """テスト用：発行されたイベントをクリア"""
        self._published_events.clear()
