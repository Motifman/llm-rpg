"""
SyncEventDispatcher - 同期ドメインイベントの即時処理を担当するディスパッチャー

Unit of Work から同期イベント処理ロジックを分離し、flush_sync_events として責務を明確化する。
PLAN Phase 5 設計: UoW とイベント処理の完全分離。
"""
from typing import TYPE_CHECKING, Any

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
        InMemoryEventPublisherWithUow,
    )


class SyncEventDispatcher:
    """同期イベントを即座に処理するディスパッチャー

    Unit of Work の保留操作を実行し、未処理の同期イベントを
    EventPublisher 経由でハンドラに配送する。
    """

    def __init__(
        self,
        unit_of_work: "InMemoryUnitOfWork",
        event_publisher: "InMemoryEventPublisherWithUow | None",
    ) -> None:
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher

    def flush_sync_events(self) -> None:
        """同期イベントを即座に処理する（同一トランザクション内）

        保留中の操作を反映したうえで、未処理の同期イベントを
        publish_sync_events 経由で処理する。
        ハンドラがさらにイベントを発行した場合はループ継続する。
        """
        if not self._unit_of_work.is_in_transaction():
            return

        if not hasattr(self._unit_of_work, "_processed_sync_count"):
            self._unit_of_work._processed_sync_count = 0

        while True:
            # 同期イベントを処理する前に、そこまでの操作を全て反映させる
            self._unit_of_work.execute_pending_operations()

            if self._unit_of_work._processed_sync_count >= len(
                self._unit_of_work._pending_events
            ):
                break

            events_to_process: list[BaseDomainEvent[Any, Any]] = self._unit_of_work._pending_events[
                self._unit_of_work._processed_sync_count :
            ]
            self._unit_of_work._processed_sync_count = len(
                self._unit_of_work._pending_events
            )
            if self._event_publisher:
                self._event_publisher.publish_sync_events(events_to_process)
