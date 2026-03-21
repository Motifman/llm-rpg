"""TransactionalScope - Phase 4: post-commit orchestration を担う wrapper

UoW の commit から非同期配信トリガーを分離し、commit 後の
get_committed_events → publish_async_events → clear_committed_events の流れを
本 scope が担う。with uow: 互換を維持するため、戻り値の第一要素として使われる。
"""
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
    from ai_rpg_world.domain.common.event_publisher import EventPublisher


class TransactionalScope:
    """UoW をラップし、commit 後の post-commit orchestration を担う

    with scope: 使用時、commit 成功後に EventPublisher.publish_async_events を呼び、
    非同期イベント配信を orchestrator 側で明示的に行う。UoW.commit は async 配信を知らない。
    """

    def __init__(self, unit_of_work: Any, event_publisher: "EventPublisher | None" = None):
        self._uow = unit_of_work
        self._event_publisher = event_publisher
        self._sync_event_dispatcher = None

    def set_event_publisher(self, event_publisher: "EventPublisher") -> None:
        """post-commit orchestration 用の EventPublisher を設定（遅延バインディング）"""
        self._event_publisher = event_publisher

    def set_sync_event_dispatcher(self, dispatcher: Any) -> None:
        """SyncEventDispatcher を設定。create_with_event_publisher で注入される。"""
        self._sync_event_dispatcher = dispatcher

    @property
    def sync_event_dispatcher(self):
        """Phase 5.2: Coordinator 等に注入する SyncEventDispatcher を返す。"""
        return self._sync_event_dispatcher

    def __enter__(self):
        self._uow.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._uow.rollback()
            return False

        self._uow.commit()

        # post-commit orchestration: committed events を非同期配信
        events = self._uow.get_committed_events()
        if events and self._event_publisher is not None:
            self._event_publisher.publish_async_events(events)
        self._uow.clear_committed_events()

        return False

    def __getattr__(self, name: str) -> Any:
        """UoW のメソッド・プロパティを委譲"""
        return getattr(self._uow, name)
