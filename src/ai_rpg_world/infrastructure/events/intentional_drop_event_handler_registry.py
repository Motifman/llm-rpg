"""意図的ドロップ（ItemDroppedFromInventoryEvent）のイベントハンドラ登録"""

from typing import TYPE_CHECKING

from ai_rpg_world.application.world.handlers.item_dropped_from_inventory_drop_handler import (
    ItemDroppedFromInventoryDropHandler,
)
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.player.event.inventory_events import ItemDroppedFromInventoryEvent

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class IntentionalDropEventHandlerRegistry:
    """ItemDroppedFromInventoryEvent の同期ハンドラ登録（同一トランザクションでドロップをアトミックに扱う）"""

    def __init__(self, item_dropped_drop_handler: ItemDroppedFromInventoryDropHandler):
        self._item_dropped_drop_handler = item_dropped_drop_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        event_publisher.register_handler(
            ItemDroppedFromInventoryEvent,
            self._create_event_handler(self._item_dropped_drop_handler.handle),
            is_synchronous=True,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
