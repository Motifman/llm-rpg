"""
InMemoryEventPublisherWithUow - Unit of Workと統合されたインメモリイベントパブリッシャー
"""
from typing import Dict, List, Optional, Tuple, Type

from ai_rpg_world.domain.common.async_event_executor import AsyncDispatchTask, AsyncEventExecutor
from ai_rpg_world.domain.common.async_event_transport import AsyncEventTransport
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class InMemoryEventPublisherWithUow(EventPublisher[DomainEvent]):
    """Unit of Workと統合されたインメモリイベントパブリッシャー

    **当面は `InMemoryUnitOfWork` 専用**（コンストラクタ引数および `is_in_transaction` /
    `get_pending_events` / `clear_pending_events` 等への依存）。`SqliteUnitOfWork` とは
    そのままでは併用できない。SQLite 永続化 UoW と同一プロセスでイベント経路を統合するには、
    別 feature で UoW を Protocol 化するなどの移行が必要（本リポジトリの sqlite-domain-repositories-uow
    feature の FOLLOWUP 参照）。

    イベントの発行をUnit of Workのトランザクション境界内で管理します。
    Phase 5: AsyncEventExecutor 注入可能。Phase 8: AsyncEventTransport 経由が優先。
    - async_transport 注入時: publish_async_events → transport.dispatch(envelopes) → executor
    - async_executor のみ注入時（後方互換）: publish_async_events → executor.execute 直呼び
    - 未注入時: インライン実行。
    """

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        async_transport: Optional[AsyncEventTransport] = None,
        *,
        async_executor: Optional[AsyncEventExecutor] = None,
    ):
        self._sync_handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}
        self._async_handlers: Dict[Type[DomainEvent], List[EventHandler[DomainEvent]]] = {}
        self._published_events: List[DomainEvent] = []
        self._pending_events: List[DomainEvent] = []
        self._unit_of_work = unit_of_work
        self._async_transport = async_transport
        self._async_executor = async_executor

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

    def _build_async_dispatch_tasks(self, events: List[DomainEvent]) -> List[AsyncDispatchTask]:
        """イベント群から (event, handler) タスク列を生成する"""
        tasks: List[AsyncDispatchTask] = []
        for event in events:
            if event not in self._published_events:
                self._published_events.append(event)
            event_type = type(event)
            handlers = self._async_handlers.get(event_type, [])
            for handler in handlers:
                tasks.append((event, handler))
        return tasks

    def publish_async_events(self, events: List[DomainEvent]) -> None:
        """指定イベントを非同期ハンドラで処理する（public handoff API）

        UoW の pending に依存せず、明示的に渡されたイベントのみを処理する。
        post-commit orchestration から呼ばれることを想定。
        Phase 8: transport 注入時は transport.dispatch、後方互換で executor のみ注入時は executor 直呼び、未注入時はインライン実行。
        """
        tasks = self._build_async_dispatch_tasks(events)
        if self._async_transport is not None:
            self._async_transport.dispatch(tasks)
        elif self._async_executor is not None:
            self._async_executor.execute(tasks)
        else:
            for event, handler in tasks:
                handler.handle(event)

    def publish_pending_events(self) -> None:
        """保留中のイベントを別トランザクションで処理（非同期ハンドラ用）

        互換 API。UoW またはパブリッシャーの pending から pull する。
        新規コードは publish_async_events(events) の push API を優先すること。
        """
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
                handler.handle(event)

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
